"""Asama 9.2: egitim kliplerinden TCN girdi pencereleri cikarir.

Klipler GERCEK hattan gecer (Preprocessor -> PoseDetector -> Tracker ->
Smoother), boylece egitim verisi uretimde gorulen iskeletle ayni gurultuyu,
ayni duzlestirmeyi ve ayni kimlik kopmalarini tasir. Ayri bir "temiz" poz
cikarim yolu yazilmaz — yazilsaydi model uretimde gormeyecegi bir dunyada
egitilmis olurdu.

Pencere duzeni (docs/ASAMA9_PLAN.md SS2), kare basina 53 kanal:

    0-33   17 keypoint (x, y), bbox'a normalize -> (kp - [x1,y1]) / [w,h]
    34-50  17 keypoint guveni
    51-52  centroid yer degistirmesi / bbox yuksekligi (dx, dy)

Kurallarin turettigi skalerler (norm_speed, body_tilt, ...) BILEREK yok:
model kuralin gordugunu degil ham iskeleti gorur, ablation tablosunun anlami
buna dayanir.

    venv/Scripts/python.exe -m eval.extract_sequences --limit 5
    venv/Scripts/python.exe -m eval.extract_sequences
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from vision.source import VideoSource
from vision.stages.features import STALE_FRAMES
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Tracker

# Pencere duzeni ve kanal sayisi modelin sozlesmesidir, burada kopyalanmaz.
from models.tcn import CHANNELS, CLASSES, MIN_POSE_RATIO, STRIDE, WINDOW, frame_vector


URFD_LABELS = "_urfd_cam0_labels.csv"
URFD_FALL_LABELS = {"0", "1"}      # 0 = dusme ani (gecis), 1 = yerde


def load_urfd_labels(path: Path) -> dict[str, set[int]]:
    """klip adi -> FALL sayilan kare indeksleri (0 tabanli).

    URFD klip basina kare bazli etiket veriyor: -1 ayakta, 0 dusme ani,
    1 yerde. Bu dosya olmadan klibin ~%40'i (dusme ONCESI yuruyus) FALL
    etiketi aliyordu ve model yuruyusu dusme saniyordu (olculdu: FALL
    kesinlik 0.300). CASIA dusme kliplerinde boyle bir anotasyon yok,
    onlar klip etiketiyle kalir — kabul edilen gurultu.
    """
    if not path.exists():
        return {}
    out: dict[str, set[int]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 3 or row[2] not in URFD_FALL_LABELS:
                continue
            out.setdefault(f"urfd_{row[0]}-cam0", set()).add(int(row[1]) - 1)
    return out


def clip_tracks(path: Path, detector: PoseDetector) -> tuple[float, dict[int, list[tuple]]]:
    """(fps, iz basina (kare indeksi, bbox, keypoints) listesi) — kare sirasinda."""
    preprocess, smoother = Preprocessor(), Smoother()
    tracker = Tracker(device=detector.device)
    per_track: dict[int, list[tuple]] = {}
    fps = 25.0
    with VideoSource(str(path)) as source:
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():
                    break
                continue
            fps = source.fps
            image = preprocess(frame.image)
            tracks = smoother(tracker.update(detector([image])[0], image),
                              frame.idx / source.fps)
            for track in tracks:
                kp = track.keypoints_smoothed if track.keypoints_smoothed is not None \
                    else track.keypoints
                per_track.setdefault(track.track_id, []).append((frame.idx, track.bbox, kp))
    return fps, per_track


def split_runs(samples: list[tuple]) -> list[list[tuple]]:
    """Iz STALE_FRAMES'ten uzun kayboluyorsa pencere zinciri kopar.

    Uretimde de oyle: FeatureEngine bu kadar gorulmeyen izin penceresini
    dusurur (vision/stages/features.py STALE_FRAMES). Daha kisa bosluklar
    korunur — pencere "son 50 GORULME"dir, 50 ardisik kare degil; kesintisiz
    50 kare sarti kliplerin neredeyse tamamini eliyordu (izler 91-198 kare
    yasiyor ama her ~15 karede bir kare atliyor).
    """
    runs, current = [], [samples[0]]
    for prev, item in zip(samples, samples[1:]):
        if item[0] - prev[0] > STALE_FRAMES:
            runs.append(current)
            current = []
        current.append(item)
    runs.append(current)
    return runs


def clip_windows(samples: list[tuple], fps: float, stride: int = STRIDE,
                 event_frames: set[int] | None = None) -> tuple[np.ndarray, int]:
    """(N, 50, 53) pencere yigini ve DUSURULEN pencere sayisi.

    `event_frames` verilirse pencere yalnizca olayin GERCEKTEN gectigi kareyi
    iceriyorsa tutulur (URFD kare bazli etiketi).
    """
    kept, dropped = [], 0
    for run in split_runs(samples):
        for start in range(0, max(len(run) - WINDOW + 1, 0), stride):
            chunk = run[start:start + WINDOW]
            if sum(kp is not None for _, _, kp in chunk) / WINDOW < MIN_POSE_RATIO:
                dropped += 1
                continue
            if event_frames is not None and not any(idx in event_frames
                                                    for idx, _, _ in chunk):
                dropped += 1
                continue
            prev_idx, prev_bbox = None, None
            window = np.empty((WINDOW, CHANNELS), dtype=np.float32)
            for i, (idx, bbox, kp) in enumerate(chunk):
                dt = (idx - prev_idx) / fps if prev_idx is not None else 0.0
                window[i] = frame_vector(bbox, kp, prev_bbox, dt)
                prev_idx, prev_bbox = idx, bbox
            kept.append(window)
    return (np.stack(kept) if kept else np.empty((0, WINDOW, CHANNELS), np.float32)), dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="Egitim kliplerinden TCN pencereleri cikarir")
    parser.add_argument("--clips", default="data/train", help="sinif klasorlerinin kokU")
    parser.add_argument("--out", default="data/sequences", help="npz hedefi")
    parser.add_argument("--classes", default=",".join(CLASSES))
    parser.add_argument("--limit", type=int, default=0, help="sinif basina klip siniri (deneme)")
    parser.add_argument("--stride", type=int, default=STRIDE,
                        help="pencere kaydirmasi; ince sinifta dusurulur")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = parser.parse_args()

    root, out_root = Path(args.clips), Path(args.out)
    detector = PoseDetector(args.weights)
    urfd = load_urfd_labels(root / URFD_LABELS)
    print(f"{'sinif':8} {'klip':>5} {'pencere':>8} {'dusen':>7} {'izsiz klip':>11}")
    for name in [c.strip().upper() for c in args.classes.split(",") if c.strip()]:
        clips = sorted((root / name).glob("*.mp4"))
        if args.limit:
            clips = clips[:args.limit]
        out_dir = out_root / name
        out_dir.mkdir(parents=True, exist_ok=True)
        total = dropped_total = empty = 0
        for clip in clips:
            target = out_dir / (clip.stem + ".npz")
            if target.exists():
                total += int(np.load(target)["x"].shape[0])
                continue
            windows, dropped = [], 0
            event_frames = urfd.get(clip.stem) if name == "FALL" else None
            fps, per_track = clip_tracks(clip, detector)
            for samples in per_track.values():
                stack, drop = clip_windows(samples, fps, args.stride, event_frames)
                dropped += drop
                if stack.shape[0]:
                    windows.append(stack)
            dropped_total += dropped
            # Pencere cikmayan klip icin de BOS npz yazilir: yoksa dosya
            # olusmaz, betik her yeniden calistirildiginda o klip bastan
            # islenirdi (yarim kalan bir kosuda 213 klip bosuna tekrar
            # ediliyordu). load_split bos diziyi zaten atliyor.
            stacked = (np.concatenate(windows) if windows
                       else np.empty((0, WINDOW, CHANNELS), np.float32))
            empty += 0 if windows else 1
            np.savez_compressed(target, x=stacked)
            total += int(stacked.shape[0])
        print(f"{name:8} {len(clips):5d} {total:8d} {dropped_total:7d} {empty:11d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
