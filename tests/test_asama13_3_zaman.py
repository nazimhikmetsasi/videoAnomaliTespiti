"""Asama 13.3b: kural, oznitelik ve izleyici pencereleri SANIYE cinsinden.

Iki sey denetlenir: (1) 25 FPS'te bosluksuz izde davranis eski kare sayili
koddakiyle ayni; (2) ayni fiziksel hareket 25, 10 ve 5 FPS'te orneklenince
ayni sonucu verir. GPU gerekmez (izleyici testi CPU'da kosar).

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_3_zaman.py -q
"""

from __future__ import annotations

import datetime
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.rules.arbiter import MODEL_EVERY_SEC, HybridArbiter  # noqa: E402
from vision.rules.engine import RuleEngine, Thresholds, Zone  # noqa: E402
from vision.rules.fall import FallRule  # noqa: E402
from vision.rules.fight import FightRule  # noqa: E402
from vision.rules.loiter import LoiterRule  # noqa: E402
from vision.rules.run import GAIT_SEC, RunRule  # noqa: E402
from vision.rules.zone import ZoneRule  # noqa: E402
from vision.stages.features import (  # noqa: E402
    EPS, RETAIN_SEC, STALE_SEC, FeatureEngine, FrameFeatures, TrackWindow)
from vision.stages.smoother import Smoother  # noqa: E402
from vision.stages.tracker import Track, Tracker  # noqa: E402

RATES = (25, 10, 5)
TH = Thresholds()
ZONE = Zone(name="z", zone_type="forbidden",
            polygon=np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]))
INSIDE, OUTSIDE = np.array([0.5, 0.5]), np.array([0.05, 0.05])


def _feat(ts: float, *, tilt=0.0, vy=0.0, speed=0.0, limb=0.0, foot=OUTSIDE,
          centroid=(500.0, 300.0)) -> FrameFeatures:
    return FrameFeatures(
        idx=int(round(ts * 25)), ts=ts, has_pose=True, height=180.0,
        centroid=np.array(centroid, dtype=float), foot=foot, aspect=0.4,
        norm_speed=speed, norm_vy=vy, body_tilt=tilt, spine_angle=tilt, knee_angle=180.0,
        limb_speed=limb)


def _window(feats: list[FrameFeatures], track_id: int = 1) -> TrackWindow:
    window = TrackWindow(track_id, maxlen=max(250, len(feats)), retain_sec=1e9)
    for f in feats:
        window.append(f)
    return window


def _grid(fps: int, t0: float, t1: float) -> list[float]:
    """[t0, t1) araligindaki kare zamanlari."""
    return [k / fps for k in range(int(round(t0 * fps)), int(round(t1 * fps)))]


def _track(tid: int, cx: float, cy: float, w: float, h: float) -> Track:
    # Tum eklemler merkezde: omurga acisi 0, body_tilt bbox'tan gelir.
    kp = np.tile(np.array([cx, cy, 0.9]), (17, 1))
    bbox = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float32)
    return Track(track_id=tid, bbox=bbox, conf=0.9, keypoints=kp)


# ------------------------------------------------------------ covering / since
def test_covering_ve_since_25_fps() -> None:
    window = _window([_feat(k / 25) for k in range(60)])
    assert len(window.covering(0.08)) == 3
    assert len(window.covering(1.96)) == 50
    assert window.covering(1.96)[0].ts == pytest.approx(window.last.ts - 1.96)
    assert len(window.since(0.56)) == 15
    assert len(window.since(0.16)) == 5


def test_covering_5_fps_en_az_iki_kare() -> None:
    window = _window([_feat(k / 5) for k in range(20)])
    assert len(window.covering(0.08)) == 2       # son kare siniri tek basina saglamaz
    assert len(window.since(0.08)) == 1          # since kismi pencereyi kabul eder


def test_covering_kisa_izde_none() -> None:
    window = _window([_feat(k / 25) for k in range(5)])
    assert window.covering(0.36) is None
    assert window.covering(0.16) is not None
    assert _window([_feat(0.0)]).covering(0.08) is None
    assert len(_window([_feat(0.0)]).since(0.56)) == 1


def test_pencere_zamanla_budanir() -> None:
    for fps in RATES:
        window = TrackWindow(1)
        for ts in _grid(fps, 0.0, 10.0):
            window.append(_feat(ts))
        assert window.covering(GAIT_SEC) is not None
        span = window.last.ts - window.frames[0].ts
        assert RETAIN_SEC - EPS <= span < RETAIN_SEC + 1.0 / fps + EPS, (fps, span)


def test_retain_gait_ten_kucuk_degil() -> None:
    assert RETAIN_SEC >= GAIT_SEC


# ------------------------------------------------------ 25 FPS esdegerligi
def test_25fps_fall_uc_karede_tetikler() -> None:
    feats = [_feat(k / 25, tilt=5.0, vy=0.1) for k in range(17)]
    feats += [_feat(17 / 25, tilt=80.0, vy=2.5), _feat(18 / 25, tilt=85.0),
              _feat(19 / 25, tilt=85.0)]
    first = None
    for n in range(1, len(feats) + 1):
        if FallRule().check(_window(feats[:n]), TH) is not None:
            first = n - 1
            break
    assert first == 19, "ucuncu yatay karede (idx 19) tetiklemeli"
    # iki karelik tutma yetmez
    two = [_feat(k / 25, tilt=5.0, vy=2.5) for k in range(18)]
    two += [_feat(18 / 25, tilt=85.0), _feat(19 / 25, tilt=85.0)]
    assert FallRule().check(_window(two), TH) is None


def test_25fps_run_10_karede_6_isabet() -> None:
    def feats(hits: int, n: int = 10) -> list[FrameFeatures]:
        return [_feat(k / 25, speed=2.5 if k < hits else 0.5, limb=0.5) for k in range(n)]
    assert RunRule().check(_window(feats(6)), TH) is not None
    assert RunRule().check(_window(feats(5)), TH) is None
    assert RunRule().check(_window(feats(10, n=9)), TH) is None     # kisa iz


def test_25fps_zone_uc_karelik_tutma() -> None:
    rule = ZoneRule([ZONE], lambda: 0.0)
    assert rule.check(_window([_feat(k / 25, foot=INSIDE) for k in range(3)]), TH) is not None
    assert rule.check(_window([_feat(0.0), _feat(0.04, foot=INSIDE), _feat(0.08, foot=INSIDE)]),
                      TH) is None


def test_25fps_fight_ucuncu_karede() -> None:
    rule, fired = FightRule(), []
    for k in range(4):
        a = _window([_feat(k / 25, limb=3.0, centroid=(500, 300))], 1)
        b = _window([_feat(k / 25, limb=3.0, centroid=(600, 300))], 2)
        fired.append(bool(rule.check_all({1: a, 2: b}, TH)))
    assert fired == [False, False, True, True]
    # seri kesilince sayac sifirlanir
    rule = FightRule()
    for k, limb in enumerate((3.0, 3.0, 0.1, 3.0, 3.0)):
        a = _window([_feat(k / 25, limb=limb, centroid=(500, 300))], 1)
        b = _window([_feat(k / 25, limb=limb, centroid=(600, 300))], 2)
        assert rule.check_all({1: a, 2: b}, TH) == []


# --------------------------------------------------------- FPS bagimsizligi
def _run_motion(fps: int) -> tuple[list, float]:
    """Yatayda 2.5 yukseklik/sn hizla 3 sn kosu; (RUN adaylari, son norm_speed)."""
    engine, cands, last = FeatureEngine(), [], 0.0
    height, speed_px = 180.0, 2.5 * 180.0
    for k, ts in enumerate(_grid(fps, 0.0, 3.0)):
        windows = engine([_track(1, 100.0 + speed_px * ts, 300.0, 60.0, height)],
                         k, ts, (540, 2000))
        cand = RunRule().check(windows[1], TH)
        if cand is not None:
            cands.append(cand)
        last = windows[1].last.norm_speed
    return cands, last


def test_kosu_her_fps_te_aday_uretir_ve_hiz_ayni() -> None:
    ref_cands, ref_speed = _run_motion(25)
    assert ref_speed == pytest.approx(2.5, rel=0.01)
    for fps in RATES:
        cands, speed = _run_motion(fps)
        # 1.96 sn'den once adim kaniti yok: aday yer degistirme yolundan gelmeli
        assert any(c.ts < 1.9 for c in cands), f"{fps} FPS: hiz yolundan aday yok"
        assert abs(speed - ref_speed) / ref_speed < 0.10, (fps, speed, ref_speed)
    assert ref_cands


def _fall_motion(fps: int) -> tuple[list, list]:
    """Aci 10 -> 80 derece 0.3 sn'de, merkez 0.6 yukseklik iner, sonra 1 sn yatis."""
    engine, cands, trace = FeatureEngine(), [], []
    for k, ts in enumerate(_grid(fps, 0.0, 2.4)):
        p = min(max((ts - 1.0) / 0.3, 0.0), 1.0)
        theta = math.radians(10.0 + 70.0 * p)
        w, h = 180.0 * math.sin(theta), 180.0 * math.cos(theta)
        windows = engine([_track(1, 500.0, 290.0 + 108.0 * p, w, h)], k, ts, (540, 960))
        last = windows[1].last
        trace.append((round(ts, 3), round(last.body_tilt, 1), round(last.norm_vy, 2)))
        cand = FallRule().check(windows[1], TH)
        if cand is not None:
            cands.append(cand)
    return cands, trace


@pytest.mark.parametrize("fps", RATES)
def test_dusme_her_fps_te_aday_uretir(fps: int) -> None:
    cands, trace = _fall_motion(fps)
    assert cands, f"{fps} FPS: FALL adayi yok; kare kare (ts, tilt, vy): {trace[:int(2.0 * fps)]}"


def _zone_motion(fps: int, inside_sec: float) -> list:
    rule, cands = ZoneRule([ZONE], lambda: 0.0), []
    feats = []
    for ts in _grid(fps, 0.0, 3.0):
        inside = 1.0 <= ts < 1.0 + inside_sec - EPS
        feats.append(_feat(ts, foot=INSIDE if inside else OUTSIDE))
        cand = rule.check(_window(feats), TH)
        if cand is not None:
            cands.append(cand)
    return cands


@pytest.mark.parametrize("fps", RATES)
def test_bolgede_bekleme_her_fps_te_aday_tek_kare_degil(fps: int) -> None:
    assert _zone_motion(fps, 0.5), f"{fps} FPS: yarim saniyelik bekleme aday uretmedi"
    assert _zone_motion(fps, 0.5 / fps) == [], f"{fps} FPS: tek kare aday uretti"


@pytest.mark.parametrize("fps", RATES)
def test_kavga_cifti_her_fps_te_aday(fps: int) -> None:
    rule, cands = FightRule(), []
    for ts in _grid(fps, 0.0, 3.0):
        limb = 3.0 if 1.0 <= ts < 1.5 else 0.1
        a = _window([_feat(ts, limb=limb, centroid=(500, 300))], 1)
        b = _window([_feat(ts, limb=limb, centroid=(600, 300))], 2)
        cands += rule.check_all({1: a, 2: b}, TH)
    assert cands, f"{fps} FPS: FIGHT adayi yok"


# ------------------------------------------------------------------- iz yasi
def test_oznitelik_iz_yasi_5fps() -> None:
    for gap, kept in ((3.4, True), (3.7, False)):
        engine = FeatureEngine()
        for ts in _grid(5, 0.0, 1.0):
            engine([_track(1, 500.0, 300.0, 60.0, 180.0)], 0, ts, (540, 960))
        t_last = 0.8
        engine([_track(2, 500.0, 300.0, 60.0, 180.0)], 0, t_last + gap, (540, 960))
        assert (1 in engine._windows) is kept, gap
        assert (1 in engine._kp_hist) is kept, gap


def test_duzleyici_iz_yasi_5fps() -> None:
    for gap, kept in ((3.4, True), (3.7, False)):
        sm = Smoother()
        for ts in _grid(5, 0.0, 1.0):
            sm([_track(1, 500.0, 300.0, 60.0, 180.0)], ts)
        sm([_track(2, 500.0, 300.0, 60.0, 180.0)], 0.8 + gap)
        assert (1 in sm._state) is kept, gap


def test_loiter_iz_yasi_5fps() -> None:
    for gap, kept in ((3.4, True), (3.7, False)):
        rule = LoiterRule()
        for ts in _grid(5, 0.0, 1.0):
            rule.check(_window([_feat(ts)], 1), TH)
        rule.check(_window([_feat(0.8 + gap)], 2), TH)
        assert (1 in rule._state) is kept, gap


def test_stale_tek_kaynak() -> None:
    import vision.rules.loiter as loiter
    import vision.stages.smoother as smoother
    assert loiter.STALE_SEC is STALE_SEC and smoother.STALE_SEC is STALE_SEC


# ------------------------------------------------------------------- hakem
class _Ctr:
    classes = ("NORMAL", "FALL", "RUN", "FIGHT")


def _arbiter() -> tuple[HybridArbiter, list[float]]:
    rules = _Rules()
    arbiter = HybridArbiter(rules, _Ctr())
    ran: list[float] = []
    arbiter._classify = lambda windows: ran.append(next(iter(windows.values())).last.ts) or {}
    return arbiter, ran


class _Rules:
    thresholds, zones = TH, []

    def __call__(self, windows):
        return []


def test_hakem_her_5_karede_bir_kosar() -> None:
    arbiter, ran = _arbiter()
    for k in range(50):
        arbiter({1: _window([_feat(k * 0.04)])})
    assert len(ran) == 10
    assert ran[:3] == pytest.approx([0.0, 0.2, 0.4])
    assert MODEL_EVERY_SEC == 0.2


def test_hakem_idx_evresi_5in_katina_denk_gelmese_de_kosar() -> None:
    arbiter, ran = _arbiter()
    for idx in (2, 7, 12, 17):                 # eski idx % 5 hic kosmuyordu
        arbiter({1: _window([_feat(idx * 0.04)])})
    assert len(ran) == 4


def test_hakem_dusuk_fps_te_her_cagrida_kosar() -> None:
    arbiter, ran = _arbiter()
    for ts in _grid(5, 0.0, 2.0):
        arbiter({1: _window([_feat(ts)])})
    assert len(ran) == 10


# ----------------------------------------------------------------- izleyici
def _fake_result(x: float):
    from ultralytics.engine.results import Boxes
    data = np.array([[x, 200, x + 60, 380, 0.9, 0.0]], dtype=np.float32)
    return SimpleNamespace(boxes=Boxes(data, (540, 960)), keypoints=None)


@pytest.mark.parametrize("fps,expected", [(25, 60), (10, 24), (5, 12)])
def test_izleyici_tampon_sureye_gore(fps: int, expected: int) -> None:
    tracker = Tracker(device="cpu", gmc_method="none")
    image = np.zeros((540, 960, 3), np.uint8)
    for k in range(120):
        tracker.update(_fake_result(100 + k), image, k / fps)
    assert tracker.max_frames_lost == expected


def test_izleyici_kopma_ortalamayi_bozmaz() -> None:
    tracker = Tracker(device="cpu", gmc_method="none")
    image = np.zeros((540, 960, 3), np.uint8)
    for k in range(40):
        tracker.update(_fake_result(100), image, k * 0.04)
    tracker.update(_fake_result(100), image, 40 * 0.04 + 30.0)      # 30 sn kopma
    assert tracker.max_frames_lost == 60
    tracker.reset()
    assert tracker.max_frames_lost >= 1 and tracker._last_ts is None


# ----------------------------------------------------------------------- D1
def _saat(hour: int):
    stamp = datetime.datetime(2026, 1, 1, hour, 0).timestamp()
    return lambda: stamp


_NIGHT = Zone(name="gece", zone_type="restricted_hours", polygon=ZONE.polygon,
              active_from=datetime.time(22, 0), active_to=datetime.time(6, 0))


def _inside_windows() -> dict:
    # ts 1970'e yakin sahne saniyesi: eski kod active_at'i buna cozuyordu
    return {1: _window([_feat(k / 25, foot=INSIDE) for k in range(3)])}


def test_d1_kisitli_saat_duvar_saatine_bakar() -> None:
    gece = RuleEngine(zones=[_NIGHT], clock=_saat(3))(_inside_windows())
    assert any(c.anomaly_type == "ZONE_VIOLATION" for c in gece)
    gunduz = RuleEngine(zones=[_NIGHT], clock=_saat(12))(_inside_windows())
    assert not any(c.anomaly_type == "ZONE_VIOLATION" for c in gunduz)


def test_d1_loiter_ayni_saati_kullanir() -> None:
    feat = _feat(0.0, foot=INSIDE)
    assert LoiterRule([_NIGHT], _saat(3))._matching_zone(feat) is _NIGHT
    assert LoiterRule([_NIGHT], _saat(12))._matching_zone(feat) is None
