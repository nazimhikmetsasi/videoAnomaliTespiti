"""Asama 13.6 paket A: kamera nabzi, dusme sonucu alarmi, yon vektoru."""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text

from api.routers.health import STALL_MIN_CANDIDATES, pulse
from api.ws.alerts import outcome_alert


# ------------------------------------------------------------------ pulse
def test_pulse_stalled_when_candidates_without_events() -> None:
    assert pulse(0, 30, 0, 5.0) == (30, True)


def test_pulse_not_stalled_with_an_event() -> None:
    assert pulse(0, 30, 1, 5.0) == (30, False)


def test_pulse_not_stalled_below_threshold() -> None:
    assert pulse(0, 10, 0, 5.0) == (10, False)
    assert pulse(0, STALL_MIN_CANDIDATES, 0, 5.0)[1] is True


def test_pulse_stale_doc_not_stalled() -> None:
    assert pulse(0, 30, 0, 120.0) == (30, False)


def test_pulse_counter_reset_uses_last() -> None:
    # surec yeniden basladi: son < ilk -> son sifirdan beri uretilen adaydir
    assert pulse(500, 25, 0, 5.0) == (25, True)


def test_pulse_short_span_not_stalled() -> None:
    # kamera yeni acildi: 20 aday Spark'in ilk olayindan once birikebilir
    assert pulse(0, 30, 0, 5.0, span_sec=30.0) == (30, False)
    assert pulse(0, 30, 0, 5.0, span_sec=60.0) == (30, True)


def test_pulse_none_inputs() -> None:
    assert pulse(None, 30, 0, 5.0) == (None, False)
    assert pulse(0, None, 0, 5.0) == (None, False)
    assert pulse(0, 30, 0, None) == (30, False)


# ------------------------------------------------------------------ cameras_health
def test_window_min_bounds_return_422() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import current_user
    from api.db.mongo import get_mongo
    from api.db.postgres import get_db
    from api.routers.health import router

    app = FastAPI()
    app.include_router(router, prefix="/api/health")
    # Bagimliliklar sahte: sinir dogrulamasi DB'ye ulasmadan 422 vermeli.
    for dep in (current_user, get_db, get_mongo):
        app.dependency_overrides[dep] = lambda: None
    client = TestClient(app)
    assert client.get("/api/health/cameras?window_min=0").status_code == 422
    assert client.get("/api/health/cameras?window_min=61").status_code == 422


def test_cameras_health_window_fields_against_real_db() -> None:
    from api.db.mongo import get_mongo
    from api.db.postgres import SessionLocal
    from api.routers.health import cameras_health

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        mongo = get_mongo()
        mongo.client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabani/mongo'ya erisilemiyor: {exc}")
    try:
        for row in cameras_health(window_min=2, db=db, mongo=mongo, _={"role": "admin"}):
            assert row.window_min == 2
            assert row.events_window >= 0
            assert isinstance(row.stalled, bool)
    finally:
        db.close()


# ------------------------------------------------------------------ outcome_alert
def _msg(outcome: str) -> dict:
    return {"camera_id": "fall_01", "track_id": 7, "fall_time": 1764000000.1,
            "outcome": outcome, "metrics": {"last_seen_ago_sec": 4.2}}


def test_outcome_alert_down_and_recovered() -> None:
    for outcome in ("down", "recovered"):
        assert outcome_alert(_msg(outcome), "Kamera 1") == {
            "kind": "fall_outcome", "camera_id": "fall_01", "camera_name": "Kamera 1",
            "track_id": 7, "fall_time": 1764000000.1, "outcome": outcome,
            "metrics": {"last_seen_ago_sec": 4.2},
        }
    assert outcome_alert(_msg("down"), None)["camera_name"] is None


def test_outcome_alert_unknown_and_malformed_are_none() -> None:
    assert outcome_alert(_msg("unknown"), "x") is None
    assert outcome_alert({"outcome": "down"}, "x") is None
    assert outcome_alert({**_msg("down"), "track_id": "7"}, "x") is None
    assert outcome_alert({**_msg("down"), "fall_time": None}, "x") is None
    assert outcome_alert({**_msg("down"), "camera_id": ""}, "x") is None
    assert outcome_alert("bozuk", "x") is None


# ------------------------------------------------------------------ build_meta
def test_build_meta_direction_vector() -> None:
    from vision.camera import build_meta
    from vision.rules.engine import Zone

    poly = np.array([[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]], dtype=np.float32)
    zones = [
        Zone(name="kapi", zone_type="direction", polygon=poly, direction_vector=(1.0, 0.0)),
        Zone(name="yasak", zone_type="forbidden", polygon=poly),
    ]
    meta = build_meta("cam1", 1, 0.0, 960, 540, 25.0, [], zones, [], {})
    assert meta["zones"][0]["direction_vector"] == [1.0, 0.0]
    assert meta["zones"][1]["direction_vector"] is None
