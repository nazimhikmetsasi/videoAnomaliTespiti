"""GET /api/notifications kontrolleri (Asama 8.3'te eklendi).

Ucun riskli kismi sorgunun kendisi (iki LEFT JOIN + filtre), saf hesap
degil -- bu yuzden gercek veritabanina karsi calisir ve DB yoksa
tests/test_asama8_2.py'deki desenle skip eder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routers.notifications import _filters, list_notifications  # noqa: E402


def test_filters_bos_parametrelerde_bos_liste() -> None:
    assert _filters(None, None, None, None) == []


def test_filters_her_parametre_bir_kosul_ekler() -> None:
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    assert len(_filters("telegram", "sent", now, now)) == 4


def _live_session():
    from api.db.postgres import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    return db


def test_list_notifications_against_real_db() -> None:
    db = _live_session()
    try:
        out = list_notifications(
            channel=None, status=None, from_=None, to=None,
            limit=5, offset=0, db=db, _={"role": "admin"},
        )
        assert out.total >= len(out.items)
        for row in out.items:
            # event_id NOT NULL; olay silinmisse anomaly_type/camera_name None
            # kalir ama satir yine listelenir (LEFT JOIN karari).
            assert row.event_id is not None
            assert row.channel in ("telegram", "fcm")
            assert row.status in ("sent", "failed")

        bos = list_notifications(
            channel="__yok__", status=None, from_=None, to=None,
            limit=5, offset=0, db=db, _={"role": "admin"},
        )
        assert bos.total == 0 and bos.items == []
    finally:
        db.close()
