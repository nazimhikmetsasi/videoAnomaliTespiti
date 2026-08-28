"""Asama 5 oz kontrolu - brokersiz, gercek Postgres/Mongo baglantisi olmadan.

Calistirma:
    venv\\Scripts\\python.exe tests/test_api_units.py

api/routers/settings.py'nin birlestirme fonksiyonlari `db: Session`
parametresini duz Python nesnesi olarak kabul ediyor -- gercek DB yerine
`.scalar()` donen sahte bir nesne verip saf mantigi test ediyoruz (SS11).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import jwt
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.auth import ALGORITHM, create_access_token  # noqa: E402
from api.config import JWT_SECRET  # noqa: E402
from api.routers.settings import get_camera_settings  # noqa: E402
from api.schemas import ZoneIn  # noqa: E402
from vision.rules.engine import RuleEngine  # noqa: E402
from vision.settings_client import SettingsClient  # noqa: E402

# infra/postgres/init.sql detection_settings varsayilanlariyla birebir.
_SETTINGS_DEFAULTS = dict(
    pose_conf=0.25, track_conf=0.30, fall_tilt_deg=45.0, fall_norm_vy=1.20,
    run_norm_speed=1.80, run_gait_speed=1.20, loiter_sec=30, fight_proximity=1.20,
    window_frames=50, spark_window_sec=3, spark_min_hits=2,
    spark_min_sec={"FALL": 0.0, "RUN": 1.0, "ZONE_VIOLATION": 1.0, "LOITERING": 2.0, "FIGHT": 0.5},
    tcn_min_conf=0.60,
)


def _fake_row(camera_id: int | None, **overrides) -> SimpleNamespace:
    data = dict(_SETTINGS_DEFAULTS)
    data.update(overrides)
    return SimpleNamespace(camera_id=camera_id,
                            updated_at=datetime.datetime.now(datetime.timezone.utc), **data)


class _FakeDB:
    """.scalar() cagrisi basina siradaki sonucu doner -- gercek SQLAlchemy
    Session yerine gecer, sorgu govdesini incelemez."""

    def __init__(self, results: list) -> None:
        self._results = list(results)

    def scalar(self, _stmt) -> object:
        return self._results.pop(0) if self._results else None


# --------------------------------------------------------------------- jwt
def test_jwt_roundtrip_same_sub_and_role() -> None:
    user = {"id": 7, "username": "canan", "role": "operator"}
    token = create_access_token(user)
    payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    assert payload["sub"] == "7"
    assert payload["role"] == "operator"


def test_jwt_expired_token_rejected() -> None:
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    token = jwt.encode({"sub": "1", "username": "x", "role": "viewer", "exp": past},
                        JWT_SECRET, algorithm=ALGORITHM)
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        raise AssertionError("suresi gecmis jeton kabul edildi")
    except jwt.ExpiredSignatureError:
        pass


# ---------------------------------------------------------------- poligon
def test_zone_polygon_needs_at_least_3_points() -> None:
    try:
        ZoneIn(camera_id=1, name="giris", zone_type="forbidden",
               polygon=[[0.1, 0.1], [0.2, 0.2]])
        raise AssertionError("2 noktali poligon kabul edildi")
    except ValidationError:
        pass


def test_zone_polygon_out_of_range_coordinate_rejected() -> None:
    try:
        ZoneIn(camera_id=1, name="giris", zone_type="forbidden",
               polygon=[[0.1, 0.1], [0.2, 0.2], [1.4, 0.2]])
        raise AssertionError("aralik disi koordinat (1.4) kabul edildi")
    except ValidationError:
        pass


def test_zone_polygon_valid_passes() -> None:
    zone = ZoneIn(camera_id=1, name="giris", zone_type="forbidden",
                   polygon=[[0.1, 0.1], [0.2, 0.2], [0.15, 0.4]])
    assert len(zone.polygon) == 3


def test_zone_direction_requires_direction_vector() -> None:
    try:
        ZoneIn(camera_id=1, name="cikis", zone_type="direction",
               polygon=[[0.1, 0.1], [0.2, 0.2], [0.15, 0.4]])
        raise AssertionError("direction_vector eksikken zone_type=direction kabul edildi")
    except ValidationError:
        pass


# ------------------------------------------------------------- esik birlesimi
def test_camera_settings_missing_falls_back_to_global() -> None:
    db = _FakeDB([None, _fake_row(None)])   # kamera satiri yok -> global'e dus
    out = get_camera_settings(3, db=db, _={"id": 1})
    assert out.source == "global"
    assert out.camera_id is None


def test_camera_settings_present_returns_camera_row() -> None:
    db = _FakeDB([_fake_row(3, fall_tilt_deg=50.0)])
    out = get_camera_settings(3, db=db, _={"id": 1})
    assert out.source == "camera"
    assert out.camera_id == 3
    assert out.fall_tilt_deg == 50.0


# ------------------------------------------------------------- settings_client
def test_settings_client_partial_json_keeps_old_and_counts_failure() -> None:
    engine = RuleEngine()
    client = SettingsClient("http://unused", "3", engine)
    old = engine.thresholds
    ok = client.apply({"updated_at": "2026-01-01T00:00:00Z", "fall_tilt_deg": 50.0})  # eksik alan
    assert ok is False
    assert client.failures == 1
    assert engine.thresholds is old


def test_settings_client_applies_hot_fields_only() -> None:
    engine = RuleEngine()
    client = SettingsClient("http://unused", "3", engine)
    data = {
        "updated_at": "2026-01-01T00:00:00Z",
        "pose_conf": 0.99, "track_conf": 0.99, "window_frames": 999,   # restart gerektirir, yok sayilmali
        "fall_tilt_deg": 50.0, "fall_norm_vy": 1.5, "run_norm_speed": 2.0,
        "run_gait_speed": 1.5, "loiter_sec": 60, "fight_proximity": 1.0,
    }
    assert client.apply(data) is True
    assert client.applied == 1
    t = engine.thresholds
    assert t.fall_tilt_deg == 50.0
    assert t.pose_conf == 0.25   # restart-gerektiren alan degismedi


def test_settings_client_same_updated_at_skips_reapply() -> None:
    engine = RuleEngine()
    client = SettingsClient("http://unused", "3", engine)
    data = {"updated_at": "2026-01-01T00:00:00Z", "fall_tilt_deg": 50.0, "fall_norm_vy": 1.5,
            "run_norm_speed": 2.0, "run_gait_speed": 1.5, "loiter_sec": 60, "fight_proximity": 1.0}
    assert client.apply(data) is True
    assert client.apply(data) is False
    assert client.applied == 1


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
