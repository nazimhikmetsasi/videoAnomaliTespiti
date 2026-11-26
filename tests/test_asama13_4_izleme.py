"""Asama 13.4 izleyici ve yayinci testleri (docs/ASAMA13_4_PLAN.md SS5).

Sentetik FrameFeatures dizileri; her senaryo 25/10/5 FPS'te kosulur.
GPU, Kafka ve veritabani gerekmez.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.publish import OUTCOME_TOPIC, CandidatePublisher, outcome_to_dict  # noqa: E402
from vision.rules.engine import Candidate, Thresholds  # noqa: E402
from vision.rules.postfall import FallOutcome, PostFallMonitor  # noqa: E402
from vision.stages.features import FrameFeatures, TrackWindow  # noqa: E402

FPS_LIST = [25, 10, 5]
T0 = 1.0         # dusme ani (sahne sn)
H = 180.0        # ayakta kutu yuksekligi
POS = (500.0, 400.0)
LYING = (80.0, 60.0, POS)       # (tilt, height, centroid)
UP = (0.0, H, POS)


def _feat(ts: float, tilt: float, h: float, c: tuple[float, float], limb: float = 0.0) -> FrameFeatures:
    return FrameFeatures(
        idx=int(round(ts * 25)), ts=ts, has_pose=True, height=h,
        centroid=np.array(c, dtype=float), foot=np.zeros(2), aspect=0.4,
        norm_speed=0.0, norm_vy=0.0, body_tilt=tilt, spine_angle=tilt, knee_angle=180.0,
        limb_speed=limb)


def _fall(ts: float, tid: int = 1, event_time: float | None = 1000.0) -> Candidate:
    return Candidate(anomaly_type="FALL", track_ids=[tid], score=1.0, idx=0, ts=ts,
                     metrics={}, thresholds_used={}, event_time=event_time)


def run(fps: int, scene, total_sec: float = 40.0, *, fall_frames=None, th=None,
        on_frame=None, decide: float = 25.0, event_time: float | None = 1000.0):
    """scene(dt) -> {track_id: (tilt, height, (cx, cy))}; dt = ts - T0.
    Dusme adayi T0 karesinde (ya da fall_frames'te) iz 1 icin uretilir."""
    th = th or Thresholds()
    mon = PostFallMonitor(decide)
    wins: dict[int, TrackWindow] = {}
    outs: list[FallOutcome] = []
    k0 = int(round(T0 * fps))
    fall_frames = [k0] if fall_frames is None else fall_frames
    for k in range(int(total_sec * fps)):
        ts = k / fps
        if on_frame:
            on_frame(k, ts, th)
        windows = {}
        for tid, (tilt, h, c) in scene(ts - T0).items():
            w = wins.setdefault(tid, TrackWindow(tid))
            w.append(_feat(ts, tilt, h, c))
            windows[tid] = w
        cands = [_fall(ts, 1, event_time)] if k in fall_frames else []
        outs.extend(mon.update(windows, cands, ts, th))
    return outs, mon


def _base(dt: float, after):
    """dt<0: ayakta; sonra after(dt)."""
    return {1: UP} if dt < -1e-9 else after(dt)


def scene_down(dt):
    return _base(dt, lambda d: {1: LYING})


def scene_recover(dt):
    return _base(dt, lambda d: {1: UP if d >= 5 - 1e-9 else LYING})


def scene_brief_up(dt):
    return _base(dt, lambda d: {1: UP if 5 - 1e-9 <= d < 6 - 1e-9 else LYING})


def scene_sit(dt):
    return _base(dt, lambda d: {1: (0.0, 0.7 * H, POS) if d >= 5 - 1e-9 else LYING})


def scene_adopt(dt):
    def after(d):
        if d <= 1 + 1e-9:
            return {1: LYING}
        return {2: (80.0, 60.0, (POS[0] + 0.3 * H, POS[1]))} if d >= 4 - 1e-9 else {}
    return _base(dt, after)


def scene_far_new(dt):
    def after(d):
        if d <= 1 + 1e-9:
            return {1: LYING}
        return {2: (0.0, H, (POS[0] + 2 * H, POS[1]))} if d >= 4 - 1e-9 else {}
    return _base(dt, after)


def scene_new_while_visible(dt):
    def after(d):
        out = {1: LYING}
        if d >= 4 - 1e-9:
            out[2] = (0.0, H, (POS[0] + 0.3 * H, POS[1]))
        return out
    return _base(dt, after)


def _frame_tol(fps: int) -> float:
    return 1.0 / fps + 1e-6


# ----------------------------------------------------------------- izleyici
@pytest.mark.parametrize("fps", FPS_LIST)
def test_1_stays_down(fps):
    outs, mon = run(fps, scene_down)
    assert len(outs) == 1 and outs[0].outcome == "down"
    assert 25.0 - 1e-6 <= outs[0].metrics["decided_after_sec"] <= 25.0 + _frame_tol(fps)
    assert outs[0].fall_ts == T0 and outs[0].fall_time == 1000.0
    assert outs[0].metrics["lying_ratio"] == 1.0 and mon.pending() == []


@pytest.mark.parametrize("fps", FPS_LIST)
def test_2_recovers(fps):
    outs, _ = run(fps, scene_recover)
    assert [o.outcome for o in outs] == ["recovered"]
    m = outs[0].metrics
    assert abs(m["recovered_after_sec"] - 5.0) <= _frame_tol(fps)
    assert abs(m["decided_after_sec"] - 7.0) <= _frame_tol(fps)
    assert m["max_height_ratio"] == pytest.approx(1.0)


@pytest.mark.parametrize("fps", FPS_LIST)
def test_3_brief_stand_is_not_recovery(fps):
    outs, _ = run(fps, scene_brief_up)
    assert [o.outcome for o in outs] == ["down"]


def scene_up_then_vanish(dt):
    return _base(dt, lambda d: {} if d >= 6 - 1e-9 else {1: UP if d >= 5 - 1e-9 else LYING})


@pytest.mark.parametrize("fps", FPS_LIST)
def test_3b_stand_then_vanish_is_not_recovery(fps):
    # 1 sn ayakta gorunup kaybolan kisi: gorulmeyen kareler ayakta sayilmaz.
    outs, _ = run(fps, scene_up_then_vanish)
    assert [o.outcome for o in outs] == ["unknown"]


@pytest.mark.parametrize("fps", FPS_LIST)
def test_4_sitting_is_unknown(fps):
    outs, _ = run(fps, scene_sit)
    assert [o.outcome for o in outs] == ["unknown"]


@pytest.mark.parametrize("fps", FPS_LIST)
def test_5_adopts_new_track_nearby(fps):
    outs, _ = run(fps, scene_adopt)
    assert [o.outcome for o in outs] == ["down"]
    assert outs[0].adopted == [2] and outs[0].track_id == 1
    assert outs[0].metrics["last_seen_ago_sec"] <= _frame_tol(fps)


@pytest.mark.parametrize("fps", FPS_LIST)
def test_6_far_new_track_not_adopted(fps):
    outs, _ = run(fps, scene_far_new)
    assert [o.outcome for o in outs] == ["down"] and outs[0].adopted == []
    assert abs(outs[0].metrics["last_seen_ago_sec"] - 24.0) <= _frame_tol(fps)


@pytest.mark.parametrize("fps", FPS_LIST)
def test_7_no_adoption_while_fallen_track_visible(fps):
    outs, _ = run(fps, scene_new_while_visible)
    assert [o.outcome for o in outs] == ["down"] and outs[0].adopted == []


@pytest.mark.parametrize("fps", FPS_LIST)
def test_8_repeated_candidates_single_monitor(fps):
    k0 = int(round(T0 * fps))
    outs, _ = run(fps, scene_down, fall_frames=list(range(k0, k0 + 5)))
    assert len(outs) == 1


@pytest.mark.parametrize("fps", FPS_LIST)
def test_9_born_lying_ref_height_is_max_of_all(fps):
    def lying_grows(dt):          # hep yatay, boy 60 -> 100: ayakta sayilmaz
        return {1: (80.0, 60.0 if dt <= 1e-9 else 100.0, POS)}
    outs, _ = run(fps, lying_grows)
    assert [o.outcome for o in outs] == ["down"]
    assert outs[0].metrics["ref_height"] == 60.0

    def upright_small(dt):        # egim < 45 ve boy >= 0.88 ref -> kalkti
        return {1: (80.0, 60.0, POS)} if dt <= 1e-9 else {1: (0.0, 60.0, POS)}
    outs, _ = run(fps, upright_small)
    assert [o.outcome for o in outs] == ["recovered"]


@pytest.mark.parametrize("fps", FPS_LIST)
def test_10_vanishes_at_fall_is_down(fps):
    outs, _ = run(fps, lambda dt: {1: UP} if dt < -1e-9 else ({1: LYING} if dt <= 1e-9 else {}))
    assert [o.outcome for o in outs] == ["down"]
    assert outs[0].metrics["seen_ratio"] == 0.0
    assert abs(outs[0].metrics["last_seen_ago_sec"] - 25.0) <= _frame_tol(fps)


@pytest.mark.parametrize("fps", FPS_LIST)
def test_11_tilt_threshold_change_applies(fps):
    tilted = (60.0, H, POS)       # egim 60, boy tam

    def scene(dt):
        return {1: UP} if dt < -1e-9 else {1: tilted}

    def raise_threshold(k, ts, th):
        if ts - T0 >= 5 - 1e-9:
            th.fall_tilt_deg = 70.0

    outs, _ = run(fps, scene, on_frame=raise_threshold)
    assert [o.outcome for o in outs] == ["recovered"]
    outs, _ = run(fps, scene)     # esik degismezse yatay kalir
    assert [o.outcome for o in outs] == ["down"]


def test_12_fps_independence():
    for scene in (scene_down, scene_recover, scene_brief_up, scene_sit, scene_adopt):
        res = {fps: run(fps, scene)[0][0] for fps in FPS_LIST}
        assert len({o.outcome for o in res.values()}) == 1
        times = [o.metrics["decided_after_sec"] for o in res.values()]
        assert max(times) - min(times) <= 1.0 / min(FPS_LIST) + 1e-6


def test_metrics_are_plain_floats_and_pending():
    outs, mon = run(25, scene_down, total_sec=10.0)
    assert outs == [] and mon.pending() == [(1, pytest.approx(10.0 - 1 / 25 - T0), True)]
    outs, _ = run(25, scene_down)
    for v in outs[0].metrics.values():
        assert type(v) is float and v == v
    json.dumps(outs[0].metrics)


# --------------------------------------------------- silahlanma (ARM_SEC)
def _cands(fps: int, a: float, b: float) -> list[int]:
    """T0+a .. T0+b arasi 0.2 sn aralikli aday kareleri."""
    k0 = int(round(T0 * fps))
    return list(range(k0 + int(round(a * fps)), k0 + int(round(b * fps)) + 1,
                      max(1, int(round(0.2 * fps)))))


def _lies_from(sec: float):
    return lambda dt: {1: LYING if dt >= sec - 1e-9 else UP}


@pytest.mark.parametrize("fps", FPS_LIST)
def test_a_standing_candidate_no_outcome(fps):
    outs, mon = run(fps, lambda dt: {1: UP}, fall_frames=_cands(fps, 0, 1))
    assert outs == [] and mon.unlanded == 1 and mon.pending() == []


@pytest.mark.parametrize("fps", FPS_LIST)
def test_b_late_landing_one_down(fps):
    outs, mon = run(fps, _lies_from(2.0), fall_frames=_cands(fps, 0, 1.5))
    assert [o.outcome for o in outs] == ["down"] and mon.unlanded == 0
    o = outs[0]
    assert o.fall_time == 1000.0
    assert abs(o.metrics["landing_after_sec"] - 2.0) <= _frame_tol(fps)
    assert abs(o.fall_ts - (T0 + 2.0)) <= _frame_tol(fps)
    assert 25.0 - 1e-6 <= o.metrics["decided_after_sec"] <= 25.0 + _frame_tol(fps)


@pytest.mark.parametrize("fps", FPS_LIST)
def test_c_landing_after_gap_closes_silently(fps):
    k0 = int(round(T0 * fps))
    frames = [k0, k0 + int(round(0.4 * fps))]
    outs, mon = run(fps, _lies_from(4.0), fall_frames=frames)
    assert outs == [] and mon.unlanded == 1


@pytest.mark.parametrize("fps", FPS_LIST)
def test_d_one_outcome_per_episode(fps):
    def scene(dt):    # yatar, 1 sn'de kalkar, 9 sn'de yeniden yatar
        return {1: UP if 1 - 1e-9 <= dt < 9 - 1e-9 else LYING}
    k10 = int(round((T0 + 10) * fps))
    outs, mon = run(fps, scene, fall_frames=_cands(fps, 0, 3) + [k10])
    assert [o.outcome for o in outs] == ["recovered", "down"]
    assert outs[1].fall_ts >= T0 + 10 - 1e-6 and mon.unlanded == 0


def test_e_fps_independence_of_late_landing():
    res = {fps: run(fps, _lies_from(2.0), fall_frames=_cands(fps, 0, 1.5))[0][0] for fps in FPS_LIST}
    land = [o.metrics["landing_after_sec"] for o in res.values()]
    assert max(land) - min(land) <= 1.0 / min(FPS_LIST) + 1e-6
    assert len({o.outcome for o in res.values()}) == 1


# ------------------------------------------------------------------ yayinci
def _outcome(fall_time: float | None = 1000.5) -> FallOutcome:
    return FallOutcome(track_id=np.int64(7), fall_ts=np.float32(12.5), fall_time=fall_time,
                       outcome="down", decided_ts=np.float64(37.5),
                       metrics={"decided_after_sec": np.float32(25.0), "seen_ratio": np.float64(0.5)},
                       adopted=[np.int64(9)])


def test_outcome_to_dict_json_safe():
    body = outcome_to_dict(_outcome(), "cam-1")
    json.dumps(body)
    assert body == {
        "schema": 1, "camera_id": "cam-1", "track_id": 7, "fall_time": 1000.5,
        "fall_ts": 12.5, "outcome": "down", "decided_ts": 37.5, "adopted": [9],
        "metrics": {"decided_after_sec": 25.0, "seen_ratio": 0.5},
    }


def test_publisher_outcome_topic_key_and_skip():
    pub = CandidatePublisher("localhost:1", "cam-o", queue_max=10)
    sent: list[tuple] = []
    pub._produce = lambda body, topic=None, key=None: sent.append((body, topic, key))
    pub.outcome(_outcome(fall_time=None))
    assert sent == [] and pub.outcomes_skipped == 1
    pub.outcome(_outcome())
    assert len(sent) == 1 and pub.outcomes_skipped == 1
    body, topic, key = sent[0]
    assert topic == OUTCOME_TOPIC == "fall-outcomes" and key == "cam-o:7"
    assert body["camera_id"] == "cam-o"
