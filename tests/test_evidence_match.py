"""Asama 6 oz kontrolu - brokersiz, veritabanisiz, sadece assert.

Calistirma:
    venv\\Scripts\\python.exe tests/test_evidence_match.py

Kanit-olay eslesmesi IKI YONLUDUR (docs/ASAMA6_PLAN.md SS8.2):
  yon 1 -- api/routers/evidence.py::_find_matching_event / create_evidence
  yon 2 -- api/workers/consumer.py::_match_pending_evidence

Ikisi de saf ORM sorgusudur (db.scalar(select(...))); gercek Postgres'in
BETWEEN filtresini burada TEKRARLAMIYORUZ -- tests/test_api_units.py'deki
_FakeDB deseniyle ayni: db.scalar() kuyruktan sirayla doner, SQL govdesini
incelemez. 3 sn tolerans disi durum, SQL'in zaten elemis gibi scalar() None
donerek temsil edilir.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId  # noqa: E402

from api.routers.evidence import _find_matching_event, create_evidence  # noqa: E402
from api.schemas import EvidenceIn  # noqa: E402
from api.workers.consumer import _match_pending_evidence  # noqa: E402


class _Row:
    """db.execute(...).first() donen tek satirlik sahte sonuc."""

    def __init__(self, value) -> None:
        self._value = value

    def first(self):
        return self._value


class _FakeDB:
    """.execute()/.scalar() kuyruktan sirayla doner, .get() sozlukten okur --
    gercek SQLAlchemy sorgu govdesini incelemez (tests/test_api_units.py'deki
    _FakeDB deseninin ayni)."""

    def __init__(self, execute_results: list | None = None, scalar_results: list | None = None,
                 get_results: dict | None = None) -> None:
        self._execute_results = list(execute_results or [])
        self._scalars = list(scalar_results or [])
        self._gets = get_results or {}
        self.added: list = []
        self.committed = False

    def execute(self, _stmt, _params=None):
        return self._execute_results.pop(0) if self._execute_results else _Row(None)

    def scalar(self, _stmt):
        return self._scalars.pop(0) if self._scalars else None

    def get(self, _model, pk):
        return self._gets.get(pk)

    def add(self, obj) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = 999


class _FakeMongo:
    """pose_sequences.update_one cagrilarini kaydeder -- SS8.2'nin iki yonu de
    pose_sequences.event_id'yi doldurmak zorundadir."""

    def __init__(self) -> None:
        self.updates: list[tuple] = []
        self.pose_sequences = SimpleNamespace(
            update_one=lambda flt, upd, *a, **k: self.updates.append((flt, upd)))


_ADMIN = {"id": 1, "role": "admin"}
_STARTED = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
# gercek bir 24 haneli ObjectId -- link_pose_sequence gecersiz id'yi sessizce eler
_REF = "665f1c2a9b3e4d5a6c7b8d9e"


# --------------------------------------------------- olay once gelirse (yon 1)
def test_event_first_then_evidence_finds_and_fills_event() -> None:
    event = SimpleNamespace(id=42, frame_path=None, clip_path=None, mongo_ref=None)
    db = _FakeDB(execute_results=[_Row((3,))], scalar_results=[event])
    mongo = _FakeMongo()
    body = EvidenceIn(camera_id="3", anomaly_type="FALL", track_key="7",
                       start_time=(_STARTED + datetime.timedelta(seconds=1)).timestamp(),
                       frame_path="frames/3_FALL_x.jpg", clip_path="clips/3_FALL_x.mp4",
                       clip_truncated=True, mongo_ref=_REF)
    out = create_evidence(body, db=db, mongo=mongo, _=_ADMIN)
    assert out.matched is True
    assert out.event_id == 42
    assert event.frame_path == "frames/3_FALL_x.jpg"
    assert event.clip_path == "clips/3_FALL_x.mp4"
    assert db.committed is True
    # Eslesse bile evidence satiri YAZILIR: events tablosunda clip_truncated
    # kolonu yok, satir atlanirsa kirpilma bilgisi tamamen kaybolurdu (SS5.2).
    assert len(db.added) == 1
    assert db.added[0].event_id == 42
    assert db.added[0].clip_truncated is True
    assert out.evidence_id == db.added[0].id
    # pose_sequences.event_id baglandi
    assert mongo.updates == [({"_id": ObjectId(_REF)}, {"$set": {"event_id": 42}})]


# ------------------------------------------------- kanit once gelirse (yon 1+2)
def test_evidence_first_creates_unmatched_row_then_event_links() -> None:
    # A: kanit POST edilir, henuz eslesen olay yok.
    db1 = _FakeDB(execute_results=[_Row((3,))], scalar_results=[None])
    mongo1 = _FakeMongo()
    body = EvidenceIn(camera_id="3", anomaly_type="FALL", track_key="7",
                       start_time=_STARTED.timestamp(), frame_path="frames/3_FALL_y.jpg",
                       mongo_ref=_REF)
    out = create_evidence(body, db=db1, mongo=mongo1, _=_ADMIN)
    assert out.matched is False
    assert len(db1.added) == 1
    pending = db1.added[0]
    assert pending.event_id is None      # eslesmeyen satir yazildi, silinmedi (SS8.2 m.2)
    assert mongo1.updates == []          # baglanacak olay yok -- Mongo'ya dokunulmadi

    # B: olay Spark'tan gecip biraz sonra eklenir -- yon 2 bekleyen kaniti bulmali.
    # Bu YOL BASKINDIR (kanit her zaman once gelir), pose_sequences.event_id'yi
    # asil dolduran yer burasidir.
    fake_event = SimpleNamespace(id=99, frame_path=None, clip_path=None, mongo_ref=None)
    db2 = _FakeDB(scalar_results=[pending], get_results={99: fake_event})
    mongo2 = _FakeMongo()
    matched = _match_pending_evidence(
        db2, event_id=99, camera_id=3, anomaly_type="FALL",
        started_at=_STARTED + datetime.timedelta(seconds=1), mongo=mongo2)
    assert matched is True
    assert pending.event_id == 99        # kanit satiri olaya baglandi
    assert fake_event.frame_path == "frames/3_FALL_y.jpg"
    assert db2.committed is True
    assert mongo2.updates == [({"_id": ObjectId(_REF)}, {"$set": {"event_id": 99}})]


# ------------------------------------------------------------- tolerans disi
def test_outside_tolerance_does_not_match_in_either_direction() -> None:
    # Yon 1: SQL BETWEEN disinda kalan olay satiri scalar()'dan hic donmez.
    db1 = _FakeDB(execute_results=[_Row((3,))], scalar_results=[None])
    body = EvidenceIn(camera_id="3", anomaly_type="FALL", track_key="7",
                       start_time=_STARTED.timestamp())
    out = create_evidence(body, db=db1, mongo=_FakeMongo(), _=_ADMIN)
    assert out.matched is False          # eslesmedi -- baglanmadi
    assert len(db1.added) == 1           # ama satir silinmeden yazildi

    found = _find_matching_event(db1, camera_id=3, anomaly_type="FALL", start_dt=_STARTED)
    assert found is None

    # Yon 2: bekleyen evidence de ayni sekilde tolerans disinda kalirsa None doner.
    db2 = _FakeDB(scalar_results=[None])
    matched = _match_pending_evidence(db2, event_id=1, camera_id=3, anomaly_type="FALL",
                                       started_at=_STARTED)
    assert matched is False
    assert db2.committed is False        # hicbir satir degismedi


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [OK]   {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [HATA] {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  [HATA] {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n  {len(tests) - failed}/{len(tests)} gecti")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
