"""Asama 2 oz kontrolu - cerceve yok, sadece assert.

Calistirma:
    venv\\Scripts\\python.exe tests/test_vision_core.py

GPU gerektirmez: takip testi sentetik tespitlerle CPU'da kosar. Model
cikariminin kendisi `vision/run.py` raporuyla dogrulanir.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.source import VideoSource, classify_source  # noqa: E402
from vision.stages.preprocess import Preprocessor, letterbox  # noqa: E402
from vision.stages.tracker import Tracker  # noqa: E402


def test_classify_source() -> None:
    assert classify_source(0) == "webcam"
    assert classify_source("0") == "webcam"
    assert classify_source("rtsp://cam/1") == "rtsp"
    assert classify_source("data/test.mp4") == "file"


def test_letterbox_keeps_aspect() -> None:
    # 16:9 kaynak tam oturur, dolgu gerekmez.
    out = letterbox(np.zeros((1080, 1920, 3), np.uint8), 960, 540)
    assert out.shape == (540, 960, 3)

    # 4:3 kaynak: genislik 720'ye duser, yanlar gri dolgu olur.
    src = np.full((480, 640, 3), 200, np.uint8)
    out = letterbox(src, 960, 540)
    assert out.shape == (540, 960, 3)
    assert out[270, 0].tolist() == [114, 114, 114], "sol kenar dolgu olmali"
    assert out[270, 480].tolist() == [200, 200, 200], "merkez goruntu olmali"

    # En-boy korunuyor mu: beyaz kare kare kalmali, ezilmemeli.
    src = np.zeros((480, 640, 3), np.uint8)
    src[200:280, 280:360] = 255           # 80x80 kare
    out = letterbox(src, 960, 540)
    ys, xs = np.where(out[:, :, 0] > 128)
    assert abs((ys.max() - ys.min()) - (xs.max() - xs.min())) <= 2, "kare ezilmis"


def test_preprocessor_clahe() -> None:
    pre = Preprocessor(clahe=True)
    assert pre._clahe is not None
    first = pre._clahe
    rng = np.random.default_rng(0)
    low_contrast = (rng.integers(100, 140, (480, 640, 3))).astype(np.uint8)

    out = pre(low_contrast)
    assert out.shape == (540, 960, 3)
    assert pre._clahe is first, "CLAHE her karede yeniden yaratilmamali"

    # Dolgu bantlari sabit oldugu icin yalnizca goruntu bolgesi karsilastirilir.
    plain = letterbox(low_contrast, 960, 540)
    left = (960 - 720) // 2
    before = cv2.cvtColor(plain[:, left:left + 720], cv2.COLOR_BGR2GRAY).std()
    after = cv2.cvtColor(out[:, left:left + 720], cv2.COLOR_BGR2GRAY).std()
    assert after > before, f"CLAHE kontrasti artirmali ({before:.1f} -> {after:.1f})"


def _write_clip(path: Path, frames: int = 40) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (320, 240))
    assert writer.isOpened(), "test videosu yazilamadi"
    for i in range(frames):
        img = np.zeros((240, 320, 3), np.uint8)
        img[100:140, i * 4 : i * 4 + 40] = 255
        writer.write(img)
    writer.release()


def test_file_source_drops_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "clip.mp4"
        _write_clip(clip, frames=40)

        with VideoSource(clip, buffer_frames=10) as source:
            idxs = []
            while (frame := source.read(timeout=5.0)) is not None:
                idxs.append(frame.idx)

        assert len(idxs) >= 30, f"cok az kare okundu: {len(idxs)}"
        assert idxs == list(range(len(idxs))), "kare sirasi bozuk veya kare atlandi"
        assert source.frames_dropped == 0, "dosya kaynagi kare atmamali"
        assert source.eof.is_set()

        buffered = source.snapshot()
        assert len(buffered) == 10, "halka tampon en son 10 kareyi tutmali"
        assert buffered[-1].idx == idxs[-1], "tamponda en yeni kare olmali"


def test_live_source_drops_oldest() -> None:
    # Is parcacigi baslatilmadan yalnizca yayin davranisi sinanir.
    source = VideoSource("rtsp://ornek/akis", buffer_frames=3)
    assert source.is_live
    for i in range(5):
        source._publish(SimpleNamespace(idx=i, ts=0.0, image=None))

    assert source._queue.qsize() == 1, "canli kaynakta tek yuva olmali"
    assert source._queue.get_nowait().idx == 4, "en yeni kare kazanmali"
    assert source.frames_dropped == 4
    assert [f.idx for f in source.snapshot()] == [2, 3, 4], "tampon en eskiyi atmali"


def _fake_result(x1: float, y1: float, x2: float, y2: float, conf: float = 0.9):
    from ultralytics.engine.results import Boxes

    data = np.array([[x1, y1, x2, y2, conf, 0.0]], dtype=np.float32)
    return SimpleNamespace(boxes=Boxes(data, (540, 960)), keypoints=None)


def test_tracker_keeps_id_across_frames() -> None:
    # GMC kapali: sentetik karede gercek kamera hareketi yok, optik akis
    # gurultuden anlamsiz donusum uretir. GMC gercek videoda olculur.
    tracker = Tracker(device="cpu", gmc_method="none")
    image = np.zeros((540, 960, 3), np.uint8)

    ids, heights = [], []
    for step in range(20):
        x = 100 + step * 8
        tracks = tracker.update(_fake_result(x, 200, x + 60, 380), image)
        if tracks:
            ids.append(tracks[0].track_id)
            heights.append(tracks[0].height)

    assert len(ids) >= 15, f"iz cok erken kayboldu: {len(ids)} kare"
    assert len(set(ids)) == 1, f"ID degisti: {sorted(set(ids))}"
    assert len(tracker.seen_ids) == 1
    # Esiklerin normalizasyon birimi: bbox yuksekligi dogru gelmeli.
    assert abs(heights[-1] - 180.0) < 5.0, f"bbox yuksekligi yanlis: {heights[-1]}"

    tracker.reset()
    assert tracker.seen_ids == set() and tracker.frames == 0


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
