"""Asama 9.4 oz kontrolu: HybridArbiter karar tablosu.

GPU ve egitilmis agirlik gerektirmez -- siniflandirici yerine sabit cevap
donen sahte nesne kullanilir; olculen sey modelin dogrulugu degil HAKEMIN
birlestirme mantigidir.

    venv\\Scripts\\python.exe -m pytest tests/test_arbiter.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.tcn import CHANNELS, WINDOW  # noqa: E402
from vision.rules.arbiter import HybridArbiter, window_tensor  # noqa: E402
from vision.rules.engine import Candidate  # noqa: E402
from vision.stages.features import FrameFeatures, TrackWindow  # noqa: E402


class FakeRules:
    """RuleEngine yerine: verilen adaylari aynen dondurur."""

    def __init__(self, candidates: list[Candidate]) -> None:
        self.candidates, self.thresholds, self.zones = candidates, None, []

    def __call__(self, windows) -> list[Candidate]:
        return list(self.candidates)


class FakeTCN:
    """Her ize ayni olasilik satirini verir."""

    classes = ("NORMAL", "FALL", "RUN", "FIGHT")

    def __init__(self, row: list[float]) -> None:
        self.row = np.array(row, dtype=np.float32)

    def __call__(self, windows: np.ndarray) -> np.ndarray:
        return np.tile(self.row, (windows.shape[0], 1))


def _feat(idx: int, has_pose: bool = True) -> FrameFeatures:
    kp = np.zeros((17, 3), dtype=np.float32) if has_pose else None
    if kp is not None:
        kp[:, 2] = 0.9
    return FrameFeatures(
        idx=idx, ts=idx / 25.0, has_pose=has_pose, height=180.0,
        centroid=np.array([500.0, 300.0]), foot=np.array([0.5, 0.9]), aspect=0.4,
        norm_speed=0.0, norm_vy=0.0, body_tilt=0.0, spine_angle=0.0, knee_angle=180.0,
        limb_speed=0.0, bbox=np.array([470.0, 200.0, 530.0, 380.0]), keypoints=kp)


def _windows(track_id: int = 1, frames: int = WINDOW, posed: int = WINDOW) -> dict:
    window = TrackWindow(track_id, maxlen=WINDOW)
    for i in range(frames):
        window.frames.append(_feat(i, has_pose=i < posed))
    return {track_id: window}


def _cand(anomaly_type: str, track_ids: list[int], score: float = 0.5) -> Candidate:
    return Candidate(anomaly_type=anomaly_type, track_ids=track_ids, score=score,
                     idx=WINDOW - 1, ts=1.0, metrics={}, thresholds_used={})


def test_window_tensor_sekli_ve_pozsuz_reddi() -> None:
    tensor = window_tensor(_windows()[1])
    assert tensor is not None and tensor.shape == (WINDOW, CHANNELS)
    # Pencere kisa: pencere kurulmaz
    assert window_tensor(_windows(frames=WINDOW - 1)[1]) is None
    # Pozlu kare orani %60'in altinda: pencere kurulmaz (MIN_POSE_RATIO)
    assert window_tensor(_windows(posed=20)[1]) is None


def test_model_yoksa_davranis_kural_motorunun_aynisi() -> None:
    rules = FakeRules([_cand("FALL", [1])])
    arbiter = HybridArbiter(rules, None)
    out = arbiter(_windows())
    assert [c.decided_by for c in out] == ["rule"]


def test_guven_esigin_altinda_kalirsa_karar_kuralda_kalir() -> None:
    arbiter = HybridArbiter(FakeRules([_cand("FALL", [1])]),
                            FakeTCN([0.30, 0.40, 0.20, 0.10]), min_conf=0.60, every=1)
    out = arbiter(_windows())
    assert len(out) == 1 and out[0].decided_by == "rule"


def test_model_tek_basina_aday_uretir() -> None:
    arbiter = HybridArbiter(FakeRules([]), FakeTCN([0.05, 0.90, 0.03, 0.02]),
                            min_conf=0.60, every=1)
    out = arbiter(_windows())
    assert len(out) == 1
    assert out[0].anomaly_type == "FALL" and out[0].decided_by == "model"
    assert out[0].score == pytest.approx(0.9, abs=1e-6)
    assert out[0].metrics["tcn_conf"] == pytest.approx(0.9, abs=1e-6)


def test_kural_ve_model_ayni_tipte_uzlasirsa_hibrit_olur() -> None:
    arbiter = HybridArbiter(FakeRules([_cand("FALL", [1], score=0.4)]),
                            FakeTCN([0.05, 0.90, 0.03, 0.02]), min_conf=0.60, every=1)
    out = arbiter(_windows())
    # Tek aday kalir: model ayni izi ikinci kez uretmez
    assert len(out) == 1
    assert out[0].decided_by == "hybrid" and out[0].score == pytest.approx(0.9, abs=1e-6)


def test_zone_ve_loitering_modele_dokunmaz() -> None:
    arbiter = HybridArbiter(FakeRules([_cand("LOITERING", [1]), _cand("ZONE_VIOLATION", [1])]),
                            FakeTCN([0.05, 0.90, 0.03, 0.02]), min_conf=0.60, every=1)
    out = arbiter(_windows())
    kararlar = {c.anomaly_type: c.decided_by for c in out}
    assert kararlar["LOITERING"] == "rule" and kararlar["ZONE_VIOLATION"] == "rule"
    # FALL modelden ayrica gelir; kural adaylari degismeden gecer
    assert any(c.anomaly_type == "FALL" and c.decided_by == "model" for c in out)


def test_model_tek_basina_fight_uretmez() -> None:
    arbiter = HybridArbiter(FakeRules([]), FakeTCN([0.02, 0.03, 0.05, 0.90]),
                            min_conf=0.60, every=1)
    assert arbiter(_windows()) == []


def test_fight_kural_yakaladiginda_hibrite_yukselir() -> None:
    arbiter = HybridArbiter(FakeRules([_cand("FIGHT", [1], score=0.5)]),
                            FakeTCN([0.02, 0.03, 0.05, 0.90]), min_conf=0.60, every=1)
    out = arbiter(_windows())
    assert len(out) == 1 and out[0].decided_by == "hybrid"
    assert out[0].score == pytest.approx(0.9, abs=1e-6)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  [OK] {name}")
