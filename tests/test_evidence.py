"""Asama 6 kanit oz kontrolu - broker'siz, veritabanisiz, GPU gerektirmez.

Calistirma:
    venv\\Scripts\\python.exe tests/test_evidence.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.evidence import (  # noqa: E402
    EpisodeTracker, EvidenceWriter, _Job, nearest_frame, select_clip_frames,
)
from vision.rules.engine import Candidate  # noqa: E402
from vision.source import Frame  # noqa: E402


def _cand(track_ids, ts, anomaly_type="FALL", score=0.5):
    return Candidate(anomaly_type=anomaly_type, track_ids=track_ids, score=score,
                      idx=int(ts * 25), ts=ts, metrics={}, thresholds_used={})


def _frame(ts: float, idx: int = 0):
    return Frame(idx=idx, ts=ts, image=None)


def test_episode_stays_open_while_candidates_flow() -> None:
    tracker = EpisodeTracker(gap_sec=3.0, min_hits=2)
    # 0.5 sn arayla iki aday: hala acik, gap gecmedi.
    closed = tracker.update("cam1", [_cand([1], 0.0)], now_ts=0.0)
    assert closed == []
    closed = tracker.update("cam1", [_cand([1], 0.5)], now_ts=0.5)
    assert closed == [], "gap suresi dolmadan epizot kapanmamali"
    assert ("cam1", "1", "FALL") in tracker._open


def test_episode_closes_after_gap() -> None:
    tracker = EpisodeTracker(gap_sec=3.0, min_hits=2)
    tracker.update("cam1", [_cand([1], 0.0), _cand([1], 0.03)], now_ts=0.03)
    closed = tracker.update("cam1", [], now_ts=3.1)  # 3.07 sn sessizlik
    assert len(closed) == 1
    ep = closed[0]
    assert ep.hits == 2 and abs(ep.duration - 0.03) < 1e-9


def test_session_passes_filters_at_closure() -> None:
    # RUN min_sec=1.0: 11 aday / 0.44 sn -- ASAMA4_PLAN.md sahte RUN'i, gecmemeli.
    tracker = EpisodeTracker(gap_sec=3.0, min_hits=2)
    cands = [_cand([9], i * 0.04, anomaly_type="RUN") for i in range(11)]
    for c in cands:
        tracker.update("cam1", [c], now_ts=c.ts)
    closed = tracker.update("cam1", [], now_ts=cands[-1].ts + 3.5)
    assert closed == [], "session_passes gecmeyen epizot kanit uretmemeli"


def test_select_clip_frames_trims_and_flags_truncation() -> None:
    frames = [_frame(ts, idx=i) for i, ts in enumerate([0.0, 1.0, 2.0, 3.0, 20.0, 21.0])]
    # Tam kapsanan aralik: [-5, 8] -- ilk 4 kare icinde, tampon disariya tasmiyor.
    selected, truncated = select_clip_frames(frames[:4], start_ts=0.0, end_ts=3.0, pad_sec=5.0)
    assert [f.idx for f in selected] == [0, 1, 2, 3]
    assert truncated, "tampon [-5,8] araligini tam kapsamiyor (ilk kare ts=0, istenen -5)"

    # Tampon aralik disindaki kareleri elemeli: [-1, 4] araliginda yalniz ilk 4 kare var.
    selected, truncated = select_clip_frames(frames, start_ts=0.0, end_ts=3.0, pad_sec=1.0)
    assert [f.idx for f in selected] == [0, 1, 2, 3]
    assert 20.0 not in [f.ts for f in selected]
    assert truncated, "son kare (ts=21) istenen ust siniri (4) kapsamiyor"

    assert select_clip_frames([], 0.0, 1.0) == ([], True)


def test_nearest_frame_picks_closest_ts() -> None:
    frames = [_frame(t, idx=i) for i, t in enumerate([0.0, 1.0, 2.5, 4.0])]
    assert nearest_frame(frames, 2.4).idx == 2
    assert nearest_frame([], 1.0) is None


def test_best_frame_is_highest_scored_candidate() -> None:
    tracker = EpisodeTracker(gap_sec=3.0, min_hits=1)
    tracker.update("cam1", [_cand([1], 0.0, score=0.4), _cand([1], 0.1, score=0.9),
                             _cand([1], 0.2, score=0.6)], now_ts=0.2)
    closed = tracker.update("cam1", [], now_ts=3.3)
    assert len(closed) == 1
    assert closed[0].best.score == 0.9
    assert closed[0].best.ts == 0.1


def test_write_queue_drops_oldest_when_full() -> None:
    source = SimpleNamespace(fps=25.0, snapshot=lambda: [])
    writer = EvidenceWriter(source, storage_dir="unused", queue_max=2)
    jobs = [_Job(episode=None, frames=[], truncated=False, pose_samples=[]) for _ in range(3)]

    writer._enqueue(jobs[0])
    writer._enqueue(jobs[1])
    assert writer._queue.qsize() == 2 and writer.dropped == 0

    writer._enqueue(jobs[2])  # kuyruk dolu -- en eski (jobs[0]) dusmeli
    assert writer._queue.qsize() == 2
    assert writer.dropped == 1
    remaining = [writer._queue.get_nowait(), writer._queue.get_nowait()]
    assert remaining == [jobs[1], jobs[2]], "en eski is dusmeli, sira korunmali"


def test_unwritten_paths_are_reported_as_none() -> None:
    """Kare secilemediyse klip/kare YAZILMAZ -- o zaman yolu da bildirilmemeli.
    Yazilmayan yolu POST etmek veritabaninda dolu gorunen ama diskte olmayan
    bir kayit birakir (GET /api/events/{id}/clip 404)."""
    source = SimpleNamespace(fps=25.0, snapshot=lambda: [])
    writer = EvidenceWriter(source, storage_dir="unused")
    posted = {}
    writer._post_evidence = lambda ep, s, e, clip, frame, trunc, ref: posted.update(
        clip=clip, frame=frame)

    tracker = EpisodeTracker(gap_sec=3.0, min_hits=1)
    tracker.update("cam1", [_cand([1], 0.0)], now_ts=0.0)
    ep = tracker.update("cam1", [], now_ts=3.5)[0]

    # Halka tampon bos: ne klip ne kare yazilabilir.
    writer._write_job(_Job(episode=ep, frames=[], truncated=True, pose_samples=[]))
    assert posted == {"clip": None, "frame": None}
    assert writer.written_clips == 0 and writer.written_frames == 0


def test_pose_buffers_of_vanished_tracks_are_pruned() -> None:
    """Gorulen her track_id icin acilan tampon sozlukte kalici olsaydi
    gunlerce donen bir kamerada sinirsiz birikirdi."""
    source = SimpleNamespace(fps=25.0, snapshot=lambda: [])
    writer = EvidenceWriter(source, storage_dir="unused")
    track = SimpleNamespace(track_id=7, bbox=(0.0, 0.0, 1.0, 1.0),
                            keypoints=None, keypoints_smoothed=None)

    writer.on_frame("cam1", 0, ts=0.0, wall_ts=0.0, tracks=[track], candidates=[])
    assert ("cam1", 7) in writer._pose

    # Iz 5 sn kayip: tampon HALA durur (POSE_BUFFER_SEC=20 sn dolmadi).
    writer.on_frame("cam1", 1, ts=5.0, wall_ts=5.0, tracks=[], candidates=[])
    assert ("cam1", 7) in writer._pose, "epizot penceresi icindeki tampon silinmemeli"

    # 25 sn kayip: artik hicbir acik epizoda lazim olamaz, silinir.
    writer.on_frame("cam1", 2, ts=25.0, wall_ts=25.0, tracks=[], candidates=[])
    assert ("cam1", 7) not in writer._pose


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
