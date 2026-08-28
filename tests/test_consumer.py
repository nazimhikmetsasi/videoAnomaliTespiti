"""Asama 5 oz kontrolu - brokersiz, DB'siz, sadece assert.

Calistirma:
    venv\\Scripts\\python.exe tests/test_consumer.py

event_to_row SAF fonksiyondur (api/workers/consumer.py SS6.2) -- DB'ye
dokunmaz, bu yuzden burada dogrudan cagrilabilir.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.workers.consumer import event_to_row  # noqa: E402


def _msg(**overrides) -> dict:
    """stream/spark_job.py'nin anomaly-events cikis semasi (out.select(...))."""
    base = {
        "schema": 1, "camera_id": "3", "anomaly_type": "FALL",
        "track_key": "7", "track_ids": [7], "hits": 2,
        "start_ts": 10.0, "end_ts": 10.04, "duration_sec": 0.04,
        "start_time": 1_700_000_000.0, "end_time": 1_700_000_000.04,
        "score": 0.91, "zone_name": None,
        "metrics": {"tilt_deg": 60.0}, "thresholds_used": {"fall_tilt_deg": 45.0},
    }
    base.update(overrides)
    return base


def test_event_to_row_full_message() -> None:
    row = event_to_row(_msg(), camera_id=3, zone_id=None)
    assert row is not None
    assert row["camera_id"] == 3
    assert row["zone_id"] is None
    assert row["anomaly_type"] == "FALL"
    assert row["track_ids"] == [7]
    assert row["severity"] == "critical"
    assert row["decided_by"] == "rule"
    assert row["status"] == "new"
    assert row["duration_ms"] == 40   # round(0.04 * 1000)
    assert row["started_at"] == datetime.datetime.fromtimestamp(
        1_700_000_000.0, tz=datetime.timezone.utc)
    assert row["ended_at"] == datetime.datetime.fromtimestamp(
        1_700_000_000.04, tz=datetime.timezone.utc)


def test_event_to_row_zone_id_passthrough() -> None:
    row = event_to_row(_msg(anomaly_type="ZONE_VIOLATION", zone_name="giris"), camera_id=3, zone_id=9)
    assert row is not None
    assert row["zone_id"] == 9
    assert row["severity"] == "high"


def test_event_to_row_unknown_anomaly_type_defaults_medium() -> None:
    # ASAMA5_PLAN.md SS6.3: bilinmeyen tip -> "medium", hata yok.
    row = event_to_row(_msg(anomaly_type="SOMETHING_NEW"), camera_id=1, zone_id=None)
    assert row is not None
    assert row["severity"] == "medium"


def test_event_to_row_missing_field_returns_none() -> None:
    msg = _msg()
    del msg["start_time"]
    assert event_to_row(msg, camera_id=1, zone_id=None) is None


def test_event_to_row_empty_message_returns_none() -> None:
    assert event_to_row({}, camera_id=1, zone_id=None) is None


def test_event_to_row_clamps_score_above_one() -> None:
    # score=1.5 gibi aralik disi skor NUMERIC(4,3) sutununa tasar, 0.999'a kirpilmali.
    row = event_to_row(_msg(score=1.5), camera_id=1, zone_id=None)
    assert row is not None
    assert row["confidence"] == 0.999


def test_event_to_row_clamps_negative_score() -> None:
    row = event_to_row(_msg(score=-0.2), camera_id=1, zone_id=None)
    assert row is not None
    assert row["confidence"] == 0.0


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
