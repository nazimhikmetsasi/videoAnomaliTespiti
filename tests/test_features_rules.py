"""Asama 3 oz kontrolu - cerceve yok, sadece assert, sentetik iskeletler.

Calistirma:
    venv\\Scripts\\python.exe tests/test_features_rules.py

GPU gerektirmez: One-Euro, oznitelik ve kural hesaplari sentetik Track/
FrameFeatures nesneleriyle CPU'da kosar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.rules.engine import RuleEngine, Thresholds, Zone  # noqa: E402
from vision.rules.fall import FallRule  # noqa: E402
from vision.rules.fight import FightRule  # noqa: E402
from vision.rules.loiter import LoiterRule  # noqa: E402
from vision.rules.run import GAIT_LOOKBACK, RunRule  # noqa: E402
from vision.rules.zone import ZoneRule  # noqa: E402
from vision.stages.features import KP, FeatureEngine, FrameFeatures, TrackWindow  # noqa: E402
from vision.stages.smoother import Smoother  # noqa: E402
from vision.stages.tracker import Track  # noqa: E402

FPS = 25.0
DT = 1.0 / FPS


def _track(track_id: int, kp: np.ndarray | None, bbox=(470.0, 200.0, 530.0, 380.0)) -> Track:
    return Track(track_id=track_id, bbox=np.array(bbox, dtype=np.float32), conf=0.9, keypoints=kp)


def _skeleton(cx: float, cy: float, scale: float = 30.0) -> np.ndarray:
    """Ayakta duran govde: cy ayak tabani (asagi buyur), cx yatay merkez."""
    kp = np.zeros((17, 3))
    kp[:, 2] = 0.9
    kp[KP["nose"]] = [cx, cy - 4 * scale, 0.9]
    kp[KP["l_sho"]] = [cx - 0.4 * scale, cy - 3 * scale, 0.9]
    kp[KP["r_sho"]] = [cx + 0.4 * scale, cy - 3 * scale, 0.9]
    kp[KP["l_wri"]] = [cx - 0.4 * scale, cy - 1.5 * scale, 0.9]
    kp[KP["r_wri"]] = [cx + 0.4 * scale, cy - 1.5 * scale, 0.9]
    kp[KP["l_hip"]] = [cx - 0.3 * scale, cy - 2 * scale, 0.9]
    kp[KP["r_hip"]] = [cx + 0.3 * scale, cy - 2 * scale, 0.9]
    kp[KP["l_knee"]] = [cx - 0.3 * scale, cy - 1 * scale, 0.9]
    kp[KP["r_knee"]] = [cx + 0.3 * scale, cy - 1 * scale, 0.9]
    kp[KP["l_ank"]] = [cx - 0.3 * scale, cy, 0.9]
    kp[KP["r_ank"]] = [cx + 0.3 * scale, cy, 0.9]
    return kp


def _feat(idx: int, *, ts: float | None = None, tilt: float = 0.0, vy: float = 0.0,
          speed: float = 0.0, knee: float = 180.0, limb: float = 0.0, height: float = 180.0,
          centroid: np.ndarray | None = None, foot: np.ndarray | None = None) -> FrameFeatures:
    return FrameFeatures(
        idx=idx, ts=DT * idx if ts is None else ts, has_pose=True, height=height,
        centroid=np.array([500.0, 300.0]) if centroid is None else centroid,
        foot=np.array([0.5, 0.9]) if foot is None else foot,
        aspect=0.4, norm_speed=speed, norm_vy=vy, body_tilt=tilt, spine_angle=tilt, knee_angle=knee,
        limb_speed=limb,
    )


def _window(track_id: int, feats: list[FrameFeatures]) -> TrackWindow:
    window = TrackWindow(track_id, maxlen=max(40, len(feats)))
    for f in feats:
        window.frames.append(f)
    return window


def test_smoother_reduces_noise() -> None:
    smoother = Smoother()
    rng = np.random.default_rng(0)
    raw, smoothed = [], []
    for i in range(300):
        x = 500.0 + rng.normal(0.0, 2.0)
        kp = _skeleton(x, 380.0)
        track = _track(1, kp)
        smoother([track], i * DT)
        raw.append(x)
        smoothed.append(track.keypoints_smoothed[KP["nose"], 0])
    raw_std, smoothed_std = np.std(raw), np.std(smoothed[50:])
    assert smoothed_std < raw_std * 0.5, f"gurultu yeterince azalmadi: {raw_std:.2f} -> {smoothed_std:.2f}"


def test_smoother_step_response_not_late() -> None:
    smoother = Smoother()
    target, before = 500.0, 400.0
    last_x = before
    for i in range(11):
        x = before if i == 0 else target
        track = _track(2, _skeleton(x, 380.0))
        smoother([track], i * DT)
        last_x = track.keypoints_smoothed[KP["nose"], 0]
    assert abs(last_x - target) < 0.10 * abs(target - before), f"basamak gecikti: {last_x}"


def test_body_tilt() -> None:
    # bbox dar ve uzun (aspect 0.11 -> box_tilt ~6 derece) + dik iskelet -> body_tilt kucuk.
    fe = FeatureEngine()
    upright = _track(3, _skeleton(500.0, 380.0), bbox=(480.0, 200.0, 500.0, 380.0))
    windows = fe([upright], 0, 0.0, (540, 960))
    assert windows[3].last.body_tilt < 10.0, windows[3].last.body_tilt

    kp = np.zeros((17, 3))
    kp[:, 2] = 0.9
    kp[KP["l_hip"]], kp[KP["r_hip"]] = [400.0, 400.0, 0.9], [400.0, 380.0, 0.9]
    kp[KP["l_sho"]], kp[KP["r_sho"]] = [500.0, 400.0, 0.9], [500.0, 380.0, 0.9]
    lying = _track(4, kp, bbox=(390.0, 370.0, 510.0, 410.0))     # yatay bbox, aspect > 1
    windows = FeatureEngine()([lying], 0, 0.0, (540, 960))
    assert abs(windows[4].last.body_tilt - 90.0) < 5.0, windows[4].last.body_tilt


def test_body_tilt_from_bbox_without_pose() -> None:
    # SS10.5#4: poz yoksa body_tilt yine de bbox aspect'inden hesaplanir (aspect
    # 1.0 -> 45 derece); spine_angle bilinmiyor sentineli -1.0 doner.
    fe = FeatureEngine()
    no_pose = _track(10, None, bbox=(400.0, 200.0, 480.0, 280.0))    # 80x80, aspect 1.0
    last = fe([no_pose], 0, 0.0, (540, 960))[10].last
    assert not last.has_pose
    assert abs(last.body_tilt - 45.0) < 1.0, last.body_tilt
    assert last.spine_angle == -1.0


def test_knee_angle() -> None:
    fe = FeatureEngine()
    straight = _track(5, _skeleton(500.0, 380.0))
    assert fe([straight], 0, 0.0, (540, 960))[5].last.knee_angle > 170.0

    kp = np.zeros((17, 3))
    kp[:, 2] = 0.9
    kp[KP["l_hip"]] = [400.0, 300.0, 0.9]
    kp[KP["l_knee"]] = [400.0, 400.0, 0.9]
    kp[KP["l_ank"]] = [500.0, 400.0, 0.9]     # kalca-diz dikey, diz-bilek yatay -> 90 derece
    kp[KP["r_hip"]] = [420.0, 300.0, 0.0]     # sag bacak guvensiz, elenir
    bent = _track(6, kp)
    knee = FeatureEngine()([bent], 0, 0.0, (540, 960))[6].last.knee_angle
    assert abs(knee - 90.0) < 5.0, knee


def test_scale_invariant_speed() -> None:
    speed_1x, speed_2x = 6.0, 12.0
    windows_1x = windows_2x = None
    fe_1x, fe_2x = FeatureEngine(), FeatureEngine()
    for i in range(10):
        ts = i * DT
        cx1, cx2 = 500 + i * speed_1x, 500 + i * speed_2x
        t1 = _track(7, _skeleton(cx1, 380.0, scale=30.0),
                     bbox=(cx1 - 30, 200.0, cx1 + 30, 380.0))
        t2 = _track(7, _skeleton(cx2, 380.0, scale=60.0),
                     bbox=(cx2 - 60, 20.0, cx2 + 60, 380.0))
        windows_1x = fe_1x([t1], i, ts, (540, 960))
        windows_2x = fe_2x([t2], i, ts, (540, 960))
    s1, s2 = windows_1x[7].last.norm_speed, windows_2x[7].last.norm_speed
    assert s1 > 0.0
    assert abs(s1 - s2) / s1 < 0.05, f"olcek degismezligi bozuldu: {s1:.4f} != {s2:.4f}"


def test_velocity_warmup_is_silent() -> None:
    # Iz dogarken kutu oturana kadar hiz uretilmemeli: kisa pencerede dt tek
    # kareye kadar duser ve titreme hiz gibi okunur (normal_01 klibi 0.4 sn'de
    # 25 RUN adayi uretiyordu). Pencere dolana kadar hiz 0.
    fe = FeatureEngine(velocity_lookback=5)
    jitter = [0.0, 14.0, -12.0, 11.0, -9.0]      # kutunun oturma titremesi
    for i, dx in enumerate(jitter):
        cx = 500.0 + dx
        track = _track(8, _skeleton(cx, 380.0, scale=30.0),
                       bbox=(cx - 30, 200.0, cx + 30, 380.0))
        last = fe([track], i, i * DT, (540, 960))[8].last
        if i < 5:
            assert last.norm_speed == 0.0, f"kare {i} hiz uretti: {last.norm_speed}"
            assert last.norm_vy == 0.0, f"kare {i} dikey hiz uretti: {last.norm_vy}"


def test_fall_rule() -> None:
    th = Thresholds()
    fall_feats = [_feat(i, tilt=5.0, vy=0.1) for i in range(17)]
    fall_feats += [_feat(17, tilt=80.0, vy=2.5), _feat(18, tilt=85.0, vy=0.2),
                   _feat(19, tilt=85.0, vy=0.1)]
    cand = FallRule().check(_window(1, fall_feats), th)
    assert cand is not None and cand.anomaly_type == "FALL"

    walk_feats = [_feat(i, tilt=5.0, vy=0.1, speed=0.3) for i in range(20)]
    assert FallRule().check(_window(2, walk_feats), th) is None


def test_run_rule() -> None:
    th = Thresholds()
    # yer degistirme kanitiyla tetikleme
    fast = [_feat(i, speed=2.5) for i in range(10)]
    cand = RunRule().check(_window(3, fast), th)
    assert cand is not None and cand.anomaly_type == "RUN"

    slow = [_feat(i, speed=0.5, limb=0.5) for i in range(10)]
    assert RunRule().check(_window(4, slow), th) is None

    # SS10.3: kamera oznesi takip ederken norm_speed dusuk kalir, ama adim
    # ritmi (limb_speed medyani) esigi asarsa yine tetiklemeli. Adim kaniti
    # GAIT_LOOKBACK kare ister; kisa pencere tetiklememelidir.
    gait_short = [_feat(i, speed=0.3, limb=1.6) for i in range(GAIT_LOOKBACK - 1)]
    assert RunRule().check(_window(5, gait_short), th) is None

    gait_only = [_feat(i, speed=0.3, limb=1.6) for i in range(GAIT_LOOKBACK)]
    cand_gait = RunRule().check(_window(6, gait_only), th)
    assert cand_gait is not None and cand_gait.anomaly_type == "RUN"

    # Yuruyuste tek adimlik sicrama: pencerenin besde biri yuksek, medyan
    # dusuk kalmali -- 10 karelik pencerede bu tetikliyordu.
    burst = [_feat(i, speed=0.3, limb=3.4 if i < GAIT_LOOKBACK // 5 else 0.4)
             for i in range(GAIT_LOOKBACK)]
    assert RunRule().check(_window(7, burst), th) is None


def test_zone_rule() -> None:
    th = Thresholds()
    zone = Zone(name="test", zone_type="forbidden",
                polygon=np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]))

    inside = [_feat(i, foot=np.array([0.5, 0.5])) for i in range(3)]
    cand = ZoneRule([zone]).check(_window(5, inside), th)
    assert cand is not None and cand.anomaly_type == "ZONE_VIOLATION"

    outside = [_feat(i, foot=np.array([0.05, 0.05])) for i in range(3)]
    assert ZoneRule([zone]).check(_window(6, outside), th) is None


def test_loiter_rule() -> None:
    th = Thresholds(loiter_sec=5)
    anchor = np.array([500.0, 300.0])

    rule = LoiterRule()
    triggered = None
    for i in range(200):
        ts = i * 0.05
        cand = rule.check(_window(7, [_feat(i, ts=ts, centroid=anchor)]), th)
        if cand is not None:
            triggered = cand
            break
    assert triggered is not None and triggered.anomaly_type == "LOITERING"

    rule_short = LoiterRule()
    early = None
    for i in range(50):    # ts en fazla 2.45 sn, loiter_sec=5'in altinda kalir
        ts = i * 0.05
        early = rule_short.check(_window(8, [_feat(i, ts=ts, centroid=anchor)]), th)
    assert early is None


def test_fight_rule() -> None:
    th = Thresholds()
    close_a = _window(1, [_feat(0, centroid=np.array([500.0, 300.0]), limb=3.0)])
    close_b = _window(2, [_feat(0, centroid=np.array([600.0, 300.0]), limb=3.0)])
    rule = FightRule()
    cands = []
    for _ in range(3):
        cands = rule.check_all({1: close_a, 2: close_b}, th)
    assert any(c.anomaly_type == "FIGHT" for c in cands)

    far_b = _window(2, [_feat(0, centroid=np.array([3000.0, 300.0]), limb=3.0)])
    rule_far = FightRule()
    cands_far = []
    for _ in range(3):
        cands_far = rule_far.check_all({1: close_a, 2: far_b}, th)
    assert cands_far == []

    calm_a = _window(1, [_feat(0, centroid=np.array([500.0, 300.0]), limb=0.1)])
    calm_b = _window(2, [_feat(0, centroid=np.array([600.0, 300.0]), limb=0.1)])
    rule_calm = FightRule()
    cands_calm = []
    for _ in range(3):
        cands_calm = rule_calm.check_all({1: calm_a, 2: calm_b}, th)
    assert cands_calm == []


def test_rule_engine_needs_pose() -> None:
    fe = FeatureEngine()
    track = _track(9, None)
    windows = fe([track], 0, 0.0, (540, 960))
    engine = RuleEngine(Thresholds())
    assert engine(windows) == []


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
