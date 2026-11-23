"""Asama 13.3c: TCN girdisi zaman izgarasi — resample, pencereleme, artirim, meta.

Yalniz sentetik veri; GPU/agirlik gerekmez.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import models.tcn as tcn  # noqa: E402
from models.tcn import (AUGMENT_FPS, CHANNELS, GRID_HZ, STRIDE_SEC, WINDOW, WINDOW_SEC,  # noqa: E402
                        TCNClassifier, augment_keep, build_split, clip_windows,
                        frame_vector, resample)
from vision.stages.features import STALE_SEC  # noqa: E402

MAIN = Path(__file__).resolve().parents[1]


def _track(fps: float, seconds: float, vx: float = 120.0, t0: float = 0.0):
    """Sabit hizli yuruyus: bbox x'te vx px/sn gider, eklemler rijit gelir."""
    n = int(round(seconds * fps))
    ts = t0 + np.arange(n) / fps
    cx = 100.0 + vx * ts
    bbox = np.stack([cx - 30, np.full(n, 200.0), cx + 30, np.full(n, 380.0)], axis=1)
    base = np.stack([np.linspace(-20, 20, 17), np.linspace(210, 370, 17)], axis=1)
    kp = np.zeros((n, 17, 3))
    kp[:, :, 0] = cx[:, None] + base[None, :, 0]
    kp[:, :, 1] = base[None, :, 1]
    kp[:, :, 2] = 0.9
    return ts, bbox, kp, np.ones(n, bool)


def _old_construction(ts, bbox, kp, has_pose) -> np.ndarray:
    out = np.empty((WINDOW, CHANNELS), np.float32)
    for i in range(WINDOW):
        out[i] = frame_vector(bbox[i], kp[i] if has_pose[i] else None,
                              bbox[i - 1] if i else None, 0.04 if i else 0.0)
    return out


def test_25fps_izgaraya_oturan_girdi_eski_yapiyla_ayni() -> None:
    rng = np.random.default_rng(3)
    ts, bbox, kp, hp = _track(25.0, 2.4)
    kp[..., 2] = rng.uniform(0.0, 1.0, kp[..., 2].shape)    # dusuk guvenli eklemler de var
    kp[..., :2] += rng.normal(0, 2.0, kp[..., :2].shape)
    hp[5] = False                                            # pozsuz kareler
    hp[20] = False
    got = resample(ts, bbox, kp, hp)
    # eski: son 50 kare, ardisik dt = 0.04 (ilk satir 0)
    old = _old_construction(ts[-WINDOW:], bbox[-WINDOW:], kp[-WINDOW:], hp[-WINDOW:])
    assert got is not None and got.shape == (WINDOW, CHANNELS)
    # ilk satirin hizi: eskide prev yok (0), yenide de prev yok
    np.testing.assert_allclose(got, old, atol=1e-5)


@pytest.mark.parametrize("fps", [10.0, 5.0])
def test_dusuk_hizda_ornek_25fps_ile_yakin(fps: float) -> None:
    ts, bbox, kp, hp = _track(fps, 3.0)
    t_end = ts[ts <= 2.8 + 1e-9][-1]
    ref = resample(*_track(25.0, 3.0), t_end=t_end)
    got = resample(ts, bbox, kp, hp, t_end=t_end)
    assert ref is not None and got is not None
    assert np.abs(got[:, :34] - ref[:, :34]).max() < 0.02
    v_ref, v_got = ref[2:, 51:53], got[2:, 51:53]
    assert np.abs(v_got - v_ref).max() <= 0.10 * np.abs(v_ref).max()


def test_kisa_iz_ve_pozsuz_cogunluk_none() -> None:
    ts, bbox, kp, hp = _track(25.0, 1.5)
    assert resample(ts, bbox, kp, hp) is None
    ts, bbox, kp, hp = _track(25.0, 2.4)
    hp[:] = False
    hp[::5] = True                  # %20 pozlu < MIN_POSE_RATIO
    assert resample(ts, bbox, kp, hp) is None


def test_guveni_dusuk_komsu_varsa_guvenli_komsunun_konumu_alinir() -> None:
    ts, bbox, kp, hp = _track(5.0, 4.0, vx=0.0)
    t_end = ts[-1] - 0.1                         # izgara noktalari orneklerin arasina duser
    j = 7
    # t_end'e en yakin iki ornek: a, b; a'da j eklemi guvenilmez
    a = int(np.searchsorted(ts, t_end + 1e-6, side="right")) - 1
    kp[a, j, :] = [999.0, 999.0, 0.1]
    kp[a + 1, j, :] = [50.0, 60.0, 0.9]
    out = resample(ts, bbox, kp, hp, t_end=ts[a + 1])
    assert out is not None
    # son satir: t_end = ts[a+1] tam bir ornege oturuyor -> o ornegin eklemi
    x1, y1, x2, y2 = bbox[a + 1]
    np.testing.assert_allclose(out[-1, 2 * j], (50.0 - x1) / (x2 - x1), atol=1e-4)
    # sondan bir onceki nokta a ile a+1 arasinda: 999 degil guvenli komsunun degeri
    k_prev = WINDOW - 2
    gt = ts[a + 1] - 1 / GRID_HZ
    assert ts[a] < gt < ts[a + 1]
    assert abs(out[k_prev, 2 * j]) < 5.0     # 999'a dogru ara deger olsaydi dev bir sayi


def _data(fps: float, seconds: float, event_frames=(), gap=None, n_extra=0) -> dict:
    ts, bbox, kp, hp = _track(fps, seconds)
    frame = np.arange(len(ts), dtype=np.int32)
    if gap is not None:                          # [lo, hi) kare araligini sil
        m = (frame < gap[0]) | (frame >= gap[1])
        frame, bbox, kp, hp = frame[m], bbox[m], kp[m], hp[m]
    return {"fps": np.float64(fps), "n_frames": np.int64(int(round(seconds * fps))),
            "frame": frame, "track": np.ones(len(frame), np.int32),
            "bbox": bbox.astype(np.float32), "kp": kp.astype(np.float32), "has_pose": hp,
            "event_frames": np.array(event_frames, np.int32)}


def test_clip_windows_stride_1sn_4sn_izde_3_pencere() -> None:
    stack, dropped = clip_windows(_data(25.0, 4.0), 1.0)
    assert stack.shape == (3, WINDOW, CHANNELS) and dropped == 0


def test_stale_sec_asan_bosluk_kosuyu_boler() -> None:
    # 12 sn iz, ortada 4 sn (> 3.6) bosluk -> iki kosu, her biri 4 sn
    d = _data(25.0, 12.0, gap=(100, 200))
    assert STALE_SEC < 4.0
    stack, _ = clip_windows(d, 1.0)
    assert stack.shape[0] == 3 + 3          # bosluk icinden pencere kurulmaz
    # bosluksuz karsilastirma: 12 sn -> 10 pencere; bolununce daha az
    assert stack.shape[0] < clip_windows(_data(25.0, 12.0), 1.0)[0].shape[0]


def test_event_frames_yalniz_olayi_kapsayan_pencereleri_tutar() -> None:
    d = _data(25.0, 8.0, event_frames=[150])     # t = 6.0 sn
    stack, dropped = clip_windows(d, 1.0)
    # sonlari 1.96, 2.96, ... 6.96, 7.96; olay [t_end-1.96, t_end] icinde: 6.96, 7.96
    assert stack.shape[0] == 2 and dropped == 5


def test_augment_keep_tohumla_belirleyici_ve_hiz_hedefte() -> None:
    a = augment_keep(5000, 25.0, 10.0, seed=7)
    b = augment_keep(5000, 25.0, 10.0, seed=7)
    c = augment_keep(5000, 25.0, 10.0, seed=8)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert a.sum() / (5000 / 25.0) == pytest.approx(10.0, rel=0.05)
    assert augment_keep(100, 15.0, 15.0, 0).all() and augment_keep(100, 15.0, 30.0, 0).all()


def _write(root: Path, cls: str, stem: str, data: dict) -> None:
    (root / cls).mkdir(parents=True, exist_ok=True)
    np.savez_compressed(root / cls / f"{stem}.npz", **data)


def _empty() -> dict:
    d = _data(25.0, 4.0)
    return {**d, "frame": d["frame"][:0], "track": d["track"][:0], "bbox": d["bbox"][:0],
            "kp": d["kp"][:0], "has_pose": d["has_pose"][:0]}


def test_build_split_klip_bazinda_ayrir_ve_anahtarlari_verir(tmp_path: Path, capsys) -> None:
    for cls in ("NORMAL", "FALL"):
        for i in range(6):
            _write(tmp_path, cls, f"{cls}_{i}", _empty() if i == 2 else _data(25.0, 5.0))
    split = build_split(tmp_path)
    assert set(split) == {"train", "val@native", "val@15", "val@10", "val@5"}
    x_tr, y_tr = split["train"]
    assert x_tr.shape[0] and x_tr.shape[1:] == (WINDOW, CHANNELS) and len(y_tr) == len(x_tr)
    for key in ("val@native", "val@15", "val@10", "val@5"):
        assert split[key][0].shape[0] > 0
    # i % 5 == 0 -> klip 0 ve 5 dogrulamada (6 klip)
    n_native = split["val@native"][0].shape[0]
    per_clip_normal = clip_windows(_data(25.0, 5.0), STRIDE_SEC)[0].shape[0]
    per_clip_fall = per_clip_normal          # kaydirma butun siniflarda ayni
    assert n_native == 2 * (per_clip_normal + per_clip_fall)
    assert "bolme" in capsys.readouterr().out


def test_meta_grid_hz_yoksa_agirlik_yuklenmeden_reddedilir(tmp_path: Path, monkeypatch) -> None:
    meta = tmp_path / "tcn_meta.json"
    meta.write_text(json.dumps({"classes": list(tcn.CLASSES), "mean": [0] * CHANNELS,
                                "std": [1] * CHANNELS}), encoding="utf-8")
    monkeypatch.setattr(tcn, "META_PATH", meta)
    monkeypatch.setattr(tcn, "WEIGHTS_PATH", tmp_path / "yok.pt")   # yuklenseydi FileNotFound
    with pytest.raises(ValueError, match="yeniden egit"):
        TCNClassifier("cpu")


def test_holdout_listesi_tracks_ve_sequences_ayni() -> None:
    tracks, seqs = MAIN / "data" / "tracks", MAIN / "data" / "sequences"
    if not (tracks.exists() and seqs.exists()):
        pytest.skip("data/tracks veya data/sequences yok")
    for cls in tcn.CLASSES:
        a = [p.stem for p in sorted((tracks / cls).glob("*.npz"))]
        b = [p.stem for p in sorted((seqs / cls).glob("*.npz"))]
        assert a == b


def test_sabitler() -> None:
    assert WINDOW_SEC == pytest.approx(1.96) and GRID_HZ == 25.0
    assert AUGMENT_FPS == (15.0, 10.0, 5.0)
