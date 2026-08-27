"""Asama 4 oz kontrolu - broker'siz, assert tabanli, GPU gerektirmez.

Calistirma:
    venv\\Scripts\\python.exe tests/test_publish.py

CandidatePublisher testi kasitli olarak ulasilamayan bir bootstrap kullanir
(localhost:1) -- "goru dongusu Kafka yuzunden durmaz" kuralinin
(ASAMA4_PLAN.md SS2) kosulabilir kanitidir: bu satirlara istisna firlamadan
ulasilmasinin kendisi testtir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stream.filters import MIN_SEC_DEFAULT_MAP, session_passes  # noqa: E402
from vision.publish import CandidatePublisher, candidate_to_dict  # noqa: E402
from vision.rules.engine import Candidate  # noqa: E402

DEFAULT_MIN_HITS = 2


def _cand(track_ids: list[int], ts: float = 1.0, zone_name: str | None = None) -> Candidate:
    return Candidate(anomaly_type="ZONE_VIOLATION", track_ids=track_ids, score=0.83,
                      idx=10, ts=ts, metrics={"norm_speed": 1.5},
                      thresholds_used={"run_norm_speed": 1.8}, zone_name=zone_name)


def test_candidate_to_dict_track_key_sorted() -> None:
    body = candidate_to_dict(_cand([7, 3]), "cam-1", epoch_base=1000.0)
    assert body["track_key"] == "3-7", body["track_key"]        # siralanmis, tireli
    assert body["event_time"] == 1001.0, body["event_time"]     # epoch_base + ts
    assert body["zone_name"] is None
    json.dumps(body)   # tum govde seri hale gelebilmeli


def test_candidate_publisher_unreachable_broker_does_not_raise() -> None:
    pub = CandidatePublisher("localhost:1", "cam-test", queue_max=10)
    pub([_cand([1]), _cand([2])])   # istisna firlatmamali
    pub.close(eos=True, timeout=2.0)   # bu da firlatmamali
    assert isinstance(pub.last_error, str)
    assert pub.failed >= 0 and pub.queued >= 0


def test_session_passes_fall_vs_normal_run() -> None:
    # docs/ASAMA4_PLAN.md SS0: gercek FALL 2 aday / 0.04 sn -- gecmeli.
    assert session_passes(2, 0.04, "FALL", DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP)
    # normal_01'in sahte RUN'i: 11 aday / 0.44 sn -- run min_sec 1.0'i gecmez, elenmeli.
    assert not session_passes(11, 0.44, "RUN", DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP)
    # Tek kare gurultusu: hits=1 hicbir zaman gecmez.
    assert not session_passes(1, 5.0, "FALL", DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP)


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
