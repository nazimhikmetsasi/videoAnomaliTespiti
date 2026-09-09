"""Asama 8.2 oz kontrolu -- eksik panel uclari (users/audit/health/quality).

Saf hesap testleri (guard fonksiyonlari, quality precision, health null
alanlari) ag/DB istemez. Gercek DB'ye karsi calisanlar test_schema_sync.py'nin
deseniyle pytest.skip eder (CI'da DB olmayabilir).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_asama8_2.py -q
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.auth import require_role  # noqa: E402
from api.db.models import Camera, User  # noqa: E402
from api.routers.analytics import build_quality_rows  # noqa: E402
from api.routers.health import _to_health_out  # noqa: E402
from api.routers.users import _guard_admin_loss, _yetki_kaybi  # noqa: E402


class _FakeDB:
    """.scalar() cagrisi basina siradaki sonucu doner (test_api_units.py'deki
    _FakeDB ile ayni desen) -- gercek Session yerine gecer."""

    def __init__(self, results: list) -> None:
        self._results = list(results)

    def scalar(self, _stmt) -> object:
        return self._results.pop(0) if self._results else None


# --------------------------------------------------------- require_role (admin)
# users.py ve audit.py'nin TUM yazma/okuma uclari bu tek fonksiyona dayanir --
# admin olmayan 403 kontrolu burada, ayri ayri her uc icin tekrarlanmaz.
def test_require_role_admin_rejects_non_admin() -> None:
    check = require_role("admin")
    try:
        check(user={"id": 1, "role": "viewer"})
        raise AssertionError("viewer admin ucuna erisebildi")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_require_role_admin_allows_admin() -> None:
    check = require_role("admin")
    user = check(user={"id": 1, "role": "admin"})
    assert user["role"] == "admin"


# --------------------------------------------------------------- users guard
def test_last_active_admin_cannot_be_deactivated() -> None:
    target = User(id=2, role="admin", is_active=True)
    db = _FakeDB([0])   # baska aktif admin yok
    try:
        _guard_admin_loss(db, target, acting={"id": 1})
        raise AssertionError("son admin pasiflestirilebildi")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_admin_deactivation_allowed_when_another_admin_active() -> None:
    target = User(id=2, role="admin", is_active=True)
    db = _FakeDB([1])   # baska en az bir aktif admin var
    _guard_admin_loss(db, target, acting={"id": 1})   # yukselmemeli


def test_self_deactivation_rejected_even_for_non_admin() -> None:
    target = User(id=1, role="viewer", is_active=True)
    db = _FakeDB([])
    try:
        _guard_admin_loss(db, target, acting={"id": 1})
        raise AssertionError("kullanici kendini pasiflestirebildi")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_already_inactive_admin_reachable_without_count_check() -> None:
    # target zaten pasif -- son-admin sayisi hic sorgulanmamali (deque bos
    # kalirsa _FakeDB.scalar None doner, kod yine de patlamamali).
    target = User(id=2, role="admin", is_active=False)
    db = _FakeDB([])
    _guard_admin_loss(db, target, acting={"id": 1})


def test_role_demotion_of_admin_sayilir_yetki_kaybi() -> None:
    # Son admin'i "viewer" yapmak da paneli admin'siz birakir -- pasiflestirme
    # ile ayni koruma calismali (8.2 gozden gecirmesinde eklendi).
    target = User(id=2, role="admin", is_active=True)
    assert _yetki_kaybi(target, {"role": "viewer"}) is True
    assert _yetki_kaybi(target, {"is_active": False}) is True


def test_zararsiz_guncelleme_yetki_kaybi_degil() -> None:
    target = User(id=2, role="admin", is_active=True)
    assert _yetki_kaybi(target, {"full_name": "Yeni Ad"}) is False
    assert _yetki_kaybi(target, {"role": "admin"}) is False
    assert _yetki_kaybi(target, {"is_active": True}) is False
    # Zaten viewer olan bir kullaniciyi operator yapmak admin sayisini etkilemez.
    assert _yetki_kaybi(User(id=3, role="viewer", is_active=True), {"role": "operator"}) is False


# ------------------------------------------------------------- quality metrikleri
def test_quality_precision_computed_from_confirmed_and_false_positive() -> None:
    rows = [
        ("FALL", "acknowledged", 3), ("FALL", "resolved", 1),
        ("FALL", "false_positive", 1), ("FALL", "new", 2),
    ]
    out = build_quality_rows(rows)
    assert len(out) == 1
    row = out[0]
    assert row.anomaly_type == "FALL"
    assert row.confirmed == 4
    assert row.false_positive == 1
    assert row.pending == 2
    assert row.total == 7
    assert row.precision == pytest.approx(4 / 5)
    assert row.recall is None
    assert row.f1 is None


def test_quality_precision_null_when_denominator_zero() -> None:
    # Yalniz 'new' (pending) -- confirmed=0, false_positive=0, payda 0.
    rows = [("LOITERING", "new", 4)]
    out = build_quality_rows(rows)
    assert out[0].precision is None
    assert out[0].pending == 4
    assert out[0].total == 4


def test_quality_multiple_types_sorted_by_name() -> None:
    rows = [("RUN", "false_positive", 5), ("FALL", "new", 1)]
    out = build_quality_rows(rows)
    assert [r.anomaly_type for r in out] == ["FALL", "RUN"]
    run_row = out[1]
    assert run_row.confirmed == 0
    assert run_row.precision == 0.0   # payda 5>0, pay 0


# ---------------------------------------------------------------- health/cameras
def test_health_missing_mongo_doc_returns_null_fields() -> None:
    cam = Camera(id=1, name="cam1")
    now = datetime.datetime.now(datetime.timezone.utc)
    out = _to_health_out(cam, None, now)
    assert out.camera_id == 1
    assert out.name == "cam1"
    assert out.fps_actual is None
    assert out.dropped is None
    assert out.age_sec is None


def test_health_with_doc_computes_age_and_fields() -> None:
    cam = Camera(id=3, name="zone_01")
    now = datetime.datetime.now(datetime.timezone.utc)
    ts = (now - datetime.timedelta(seconds=30)).replace(tzinfo=None)   # BSON Date, naive
    doc = {"ts": ts, "fps_actual": 24.5, "dropped": 2, "infer_ms": 12.3,
           "gpu_mem": 100, "queue_depth": 0}
    out = _to_health_out(cam, doc, now)
    assert out.fps_actual == 24.5
    assert out.dropped == 2
    assert out.age_sec == pytest.approx(30.0, abs=1.0)


# --------------------------------------------------------- gercek DB'ye karsi
def _live_session():
    from api.db.postgres import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    return db


def test_list_audit_filters_against_real_db() -> None:
    from api.routers.audit import list_audit

    db = _live_session()
    try:
        out = list_audit(
            user_id=None, action="__asama8_2_no_such_action__", entity=None,
            from_=None, to=None, limit=10, offset=0, db=db, _={"role": "admin"},
        )
        assert out.total == 0
        assert out.items == []
    finally:
        db.close()


def test_cameras_health_against_real_db_handles_empty_collection() -> None:
    from api.db.mongo import get_mongo
    from api.routers.health import cameras_health

    db = _live_session()
    try:
        mongo = get_mongo()
        mongo.client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"mongo'ya erisilemiyor: {exc}")
    try:
        out = cameras_health(db=db, mongo=mongo, _={"role": "admin"})
        assert isinstance(out, list)
        for row in out:
            assert row.camera_id is not None
            assert row.name
    finally:
        db.close()
