"""Asama 13.5 (gorur tarafi): ters yon, bolgede kosma, canli bolge yukleme.

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_5_yon.py -q
"""

from __future__ import annotations

import datetime
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.camera import load_zones  # noqa: E402
from vision.rules.arbiter import HybridArbiter  # noqa: E402
from vision.rules.direction import DirectionRule  # noqa: E402
from vision.rules.engine import Candidate, RuleEngine, Thresholds, Zone  # noqa: E402
from vision.rules.loiter import LoiterRule  # noqa: E402
from vision.rules.zone import upgrade_run_in_zone  # noqa: E402
from vision.settings_client import SettingsClient, zones_from_api  # noqa: E402
from vision.stages.features import FrameFeatures, TrackWindow  # noqa: E402
from vision.stages.preprocess import FRAME_H, FRAME_W  # noqa: E402

RATES = (25, 10, 5)
TH = Thresholds()
SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
H = 200.0   # bbox yuksekligi, px


def _zone(vec=(1.0, 0.0), **kw) -> Zone:
    return Zone(name="koridor", zone_type="direction",
                polygon=np.array(SQUARE, dtype=np.float32), direction_vector=vec, **kw)


def _feat(ts: float, foot) -> FrameFeatures:
    return FrameFeatures(
        idx=int(round(ts * 25)), ts=ts, has_pose=True, height=H,
        centroid=np.array([500.0, 300.0]), foot=np.array(foot, dtype=float), aspect=0.4,
        norm_speed=0.0, norm_vy=0.0, body_tilt=0.0, spine_angle=0.0, knee_angle=180.0,
        limb_speed=0.0)


def _walk(fps: int, sec: float, pos) -> TrackWindow:
    """pos(t) -> normalize ayak; [0, sec] araligi fps ile orneklenir."""
    w = TrackWindow(1, maxlen=1000, retain_sec=1e9)
    for k in range(int(round(sec * fps)) + 1):
        t = k / fps
        w.append(_feat(t, pos(t)))
    return w


def _linear(speed_boy: float, axis_px, start=(0.5, 0.5)):
    """Piksel uzayinda `axis_px` yonunde speed_boy (boy/sn) hizla dogrusal hareket."""
    ux, uy = axis_px
    n = math.hypot(ux, uy)
    vx = speed_boy * H * ux / n / FRAME_W
    vy = speed_boy * H * uy / n / FRAME_H
    return lambda t: (start[0] + vx * t, start[1] + vy * t)


def _rule(*zones: Zone, clock=lambda: 0.0) -> DirectionRule:
    return DirectionRule(list(zones), clock)


# 1-6 ------------------------------------------------------------------------
@pytest.mark.parametrize("fps", RATES)
def test_ters_yon_aday_uretir(fps: int) -> None:
    cand = _rule(_zone()).check(_walk(fps, 2.0, _linear(0.5, (-1, 0))), TH)
    assert cand is not None and cand.anomaly_type == "WRONG_DIRECTION"
    assert cand.zone_name == "koridor"
    assert cand.score == pytest.approx(1.0)
    assert cand.metrics["against_speed"] == pytest.approx(0.5, rel=0.05)


@pytest.mark.parametrize("fps", RATES)
def test_ayni_yon_aday_yok(fps: int) -> None:
    assert _rule(_zone()).check(_walk(fps, 2.0, _linear(0.5, (1, 0))), TH) is None


@pytest.mark.parametrize("fps", RATES)
def test_dik_yurume_aday_yok(fps: int) -> None:
    assert _rule(_zone()).check(_walk(fps, 2.0, _linear(0.5, (0, -1))), TH) is None


@pytest.mark.parametrize("fps", RATES)
def test_yerinde_salinma_aday_yok(fps: int) -> None:
    amp = 0.05 * H / FRAME_W          # +-0.05 boy, 2 Hz

    def pos(t):
        return (0.5 + amp * math.sin(2 * math.pi * 2.0 * t), 0.5)
    for sec in (1.0, 1.1, 1.25, 2.0):   # farkli faz sonlari
        assert _rule(_zone()).check(_walk(fps, sec, pos), TH) is None


@pytest.mark.parametrize("fps", RATES)
def test_yavas_ters_yon_aday_yok(fps: int) -> None:
    assert _rule(_zone()).check(_walk(fps, 2.0, _linear(0.15, (-1, 0))), TH) is None


@pytest.mark.parametrize("fps", RATES)
def test_bolge_disi_ve_genc_iz_aday_yok(fps: int) -> None:
    small = Zone(name="k", zone_type="direction", direction_vector=(1.0, 0.0),
                 polygon=np.array([[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]],
                                  dtype=np.float32))
    assert _rule(small).check(_walk(fps, 2.0, _linear(0.5, (-1, 0))), TH) is None
    assert _rule(_zone()).check(_walk(fps, 0.8, _linear(0.5, (-1, 0))), TH) is None


# 7 --------------------------------------------------------------------------
def test_16_9_aci_piksel_uzayinda_olculur() -> None:
    zone = _zone(vec=(0.0, 1.0))      # asagi
    # Hareket normalize (1, -1): ters yonden 45 derece gorunur, pikselde
    # atan(960/540) ~ 60.6 derece -> sinirin disinda.
    w = _walk(25, 1.0, lambda t: (0.4 + 0.15 * t, 0.7 - 0.15 * t))
    assert _rule(zone).check(w, TH) is None
    # Piksel uzayinda tam ters (yukari)
    assert _rule(zone).check(_walk(25, 1.0, lambda t: (0.5, 0.7 - 0.15 * t)), TH) is not None


# 8 --------------------------------------------------------------------------
def test_saatli_yon_bolgesi_saat_disinda_aday_yok() -> None:
    zone = _zone(active_from=datetime.time(9, 0), active_to=datetime.time(17, 0))

    def stamp(h):
        return datetime.datetime(2026, 1, 5, h, 0).timestamp()
    w = _walk(25, 2.0, _linear(0.5, (-1, 0)))
    assert _rule(zone, clock=lambda: stamp(12)).check(w, TH) is not None
    assert _rule(zone, clock=lambda: stamp(20)).check(w, TH) is None


# 9 --------------------------------------------------------------------------
def _cand(kind: str, tid: int = 1) -> Candidate:
    return Candidate(anomaly_type=kind, track_ids=[tid], score=1.0, idx=0, ts=0.0,
                     metrics={}, thresholds_used={})


def test_run_zone_donusumu() -> None:
    inside, outside = (0.5, 0.5), (0.9, 0.9)
    box = np.array([[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]], dtype=np.float32)
    now = datetime.datetime(2026, 1, 5, 12, 0).timestamp()
    forb = Zone(name="yasak", zone_type="forbidden", polygon=box)
    closed = Zone(name="kapali", zone_type="restricted_hours", polygon=box,
                  active_from=datetime.time(22, 0), active_to=datetime.time(23, 0))
    open_ = Zone(name="acik", zone_type="restricted_hours", polygon=box,
                 active_from=datetime.time(9, 0), active_to=datetime.time(17, 0))
    direction = Zone(name="yon", zone_type="direction", polygon=box, direction_vector=(1, 0))

    def run(zones, foot, kind="RUN"):
        w = {1: _walk(25, 0.2, lambda t: foot)}
        return upgrade_run_in_zone([_cand(kind)], w, zones, now)[0]

    c = run([forb], inside)
    assert (c.anomaly_type, c.zone_name) == ("RUN_ZONE", "yasak")
    assert run([forb], outside).anomaly_type == "RUN"
    assert run([closed], inside).anomaly_type == "RUN"
    assert run([open_], inside).anomaly_type == "RUN_ZONE"
    assert run([direction], inside).anomaly_type == "RUN"
    assert run([forb], inside, kind="FALL").anomaly_type == "FALL"


# 10 -------------------------------------------------------------------------
def _window_single(f: FrameFeatures) -> TrackWindow:
    w = TrackWindow(9, maxlen=10, retain_sec=1e9)
    w.append(f)
    return w


def test_loiter_yalniz_yon_bolgesiyle_capa_modunda_tetiklenir() -> None:
    rule = LoiterRule([_zone()], lambda: 0.0)
    th = Thresholds(loiter_sec=5)
    got = []
    for i in range(200):
        c = rule.check(_window_single(_feat(i * 0.04, (0.5, 0.5))), th)
        if c is not None:
            got.append(c)
    assert got and got[0].anomaly_type == "LOITERING" and got[0].zone_name is None


# 11 -------------------------------------------------------------------------
def test_set_zones_sonraki_cagrida_etkili_ve_hakemden_gecer() -> None:
    walker = _walk(25, 2.0, _linear(0.5, (-1, 0)))
    engine = RuleEngine(clock=lambda: 0.0)
    assert engine({1: walker}) == []
    engine.set_zones([_zone()])
    assert [c.anomaly_type for c in engine({1: walker})] == ["WRONG_DIRECTION"]
    engine.set_zones([])
    assert engine({1: walker}) == []

    arbiter = HybridArbiter(RuleEngine(clock=lambda: 0.0))
    arbiter.set_zones([_zone()])
    assert len(arbiter.zones) == 1
    assert [c.anomaly_type for c in arbiter({1: walker})] == ["WRONG_DIRECTION"]


# 12 -------------------------------------------------------------------------
def _item(name="a", **kw) -> dict:
    d = {"name": name, "zone_type": "forbidden", "polygon": SQUARE, "is_active": True}
    d.update(kw)
    return d


def test_zones_from_api_ayrisir() -> None:
    errors: list[str] = []
    zones = zones_from_api([
        _item("pasif", is_active=False),
        _item("yon", zone_type="direction", direction_vector=[1, 0]),
        _item("saatli", zone_type="restricted_hours",
              active_from="09:00:00", active_to="17:30"),
        {"name": "bozuk"},
    ], errors)
    assert [z.name for z in zones] == ["yon", "saatli"]
    assert zones[0].direction_vector == (1.0, 0.0)
    assert zones[1].active_from == datetime.time(9, 0)
    assert zones[1].active_to == datetime.time(17, 30)
    assert zones[1].direction_vector is None
    assert len(errors) == 1


def test_apply_zones_degisimde_bir_kez_uygular() -> None:
    engine = RuleEngine()
    client = SettingsClient("http://unused", "kam", engine)
    assert client.apply_zones([_item("a"), {"name": "bozuk"}, _item("b")]) is True
    assert [z.name for z in engine.zones] == ["a", "b"]
    assert client.failures == 1
    assert client.apply_zones([_item("a"), {"name": "bozuk"}, _item("b")]) is False
    assert client.zones_applied == 1
    assert client.apply_zones([]) is True            # bos liste bolgeleri temizler
    assert engine.zones == [] and client.zones_applied == 2
    assert client.apply_zones([]) is False


def test_poll_once_bolge_hatasi_esigi_etkilemez(monkeypatch) -> None:
    import httpx
    import vision.settings_client as sc

    class _Resp:
        def __init__(self, data):
            self._d = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._d

    def fake_get(url, **kw):
        if "/api/zones" in url:
            assert kw["params"] == {"camera_id": "kam"}
            raise httpx.ConnectError("yok")
        return _Resp({"updated_at": "t", "fall_tilt_deg": 50.0, "fall_norm_vy": 1.5,
                      "run_norm_speed": 2.0, "run_gait_speed": 1.5, "loiter_sec": 60,
                      "fight_proximity": 1.0})
    monkeypatch.setattr(sc.httpx, "get", fake_get)
    client = SettingsClient("http://x/", "kam", RuleEngine())
    client._poll_once()
    assert client.applied == 1 and client.failures == 1 and client.zones_applied == 0


# 13 -------------------------------------------------------------------------
def test_load_zones_direction_vector_okur(tmp_path) -> None:
    path = tmp_path / "z.json"
    path.write_text(json.dumps({"klip": [
        {"name": "y", "zone_type": "direction", "polygon": SQUARE,
         "direction_vector": [0.5, -0.25]},
        {"name": "f", "zone_type": "forbidden", "polygon": SQUARE},
    ]}), encoding="utf-8")
    zones = load_zones(str(path), "klip")
    assert zones[0].direction_vector == (0.5, -0.25)
    assert zones[1].direction_vector is None
