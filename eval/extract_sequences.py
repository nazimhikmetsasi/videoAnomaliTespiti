"""Egitim kliplerinden HAM iz dosyalari cikarir (Asama 9.2, 13.3'te yeniden).

Klipler GERCEK hattan gecer (Preprocessor -> PoseDetector -> Tracker ->
Smoother), boylece egitim verisi uretimde gorulen iskeletle ayni gurultuyu,
ayni duzlestirmeyi ve ayni kimlik kopmalarini tasir. Ayri bir "temiz" poz
cikarim yolu yazilmaz — yazilsaydi model uretimde gormeyecegi bir dunyada
egitilmis olurdu.

Pencere BURADA kurulmaz: kare dusurme artirimi ham iz ister ve YOLO'yu her
egitimde yeniden kosmak kabul edilemez. Pencereleme `models/tcn.py`'de
(clip_windows / build_split). Kare basina kanal duzeni de orada
(frame_vector); kurallarin turettigi skalerler BILEREK yok: model kuralin
gordugunu degil ham iskeleti gorur, ablation tablosunun anlami buna dayanir.

Cikti: data/tracks/<SINIF>/<klip>.npz
    fps, n_frames (okunan kare), frame (n,) kaynak kare indeksi, track (n,),
    bbox (n,4), kp (n,17,3) (pozsuzda sifir), has_pose (n,),
    event_frames (m,) (URFD FALL kareleri; yalniz FALL klibinde, yoksa bos)
ts = frame / fps her yerde. Iz yoksa BOS dosya yazilir: yeniden baslatilan
kosu klibi tekrar islemez ve siralama (dolayisiyla egitim/dogrulama bolmesi)
degismez.

    venv/Scripts/python.exe -m eval.extract_sequences --limit 5
    venv/Scripts/python.exe -m eval.extract_sequences
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np

from vision.source import VideoSource
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Tracker

from models.tcn import CLASSES


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


def clip_tracks(path: Path, detector: PoseDetector) -> tuple[float, int, dict[int, list[tuple]]]:
    """(fps, okunan kare, iz basina (kare indeksi, bbox, keypoints) listesi) — kare sirasinda."""
    preprocess, smoother = Preprocessor(), Smoother()
    tracker = Tracker(device=detector.device)
    per_track: dict[int, list[tuple]] = {}
    fps, n_frames = 25.0, 0
    with VideoSource(str(path)) as source:
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():
                    break
                continue
            fps = source.fps
            n_frames += 1
            image = preprocess(frame.image)
            ts = frame.idx / source.fps
            tracks = smoother(tracker.update(detector([image])[0], image, ts), ts)
            for track in tracks:
                kp = track.keypoints_smoothed if track.keypoints_smoothed is not None                     else track.keypoints
                per_track.setdefault(track.track_id, []).append((frame.idx, track.bbox, kp))
    return fps, n_frames, per_track


def pack(fps: float, n_frames: int, per_track: dict[int, list[tuple]],
         events: set[int] | None) -> dict[str, np.ndarray]:
    """Iz listelerini npz alanlarina duzlestirir (kare sirasi, sonra iz)."""
    rows = sorted((idx, tid, bbox, kp) for tid, samples in per_track.items()
                  for idx, bbox, kp in samples)
    n = len(rows)
    kp_arr = np.zeros((n, 17, 3), np.float32)
    has_pose = np.zeros(n, bool)
    for i, (_, _, _, kp) in enumerate(rows):
        if kp is not None:
            kp_arr[i], has_pose[i] = kp, True
    return {
        "fps": np.float64(fps), "n_frames": np.int64(n_frames),
        "frame": np.array([r[0] for r in rows], np.int32),
        "track": np.array([r[1] for r in rows], np.int32),
        "bbox": np.array([r[2] for r in rows], np.float32).reshape(n, 4),
        "kp": kp_arr, "has_pose": has_pose,
        "event_frames": np.array(sorted(events or ()), np.int32),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Egitim kliplerinden ham iz dosyalari cikarir")
    parser.add_argument("--clips", default="data/train", help="sinif klasorlerinin kokU")
    parser.add_argument("--out", default="data/tracks", help="npz hedefi")
    parser.add_argument("--classes", default=",".join(CLASSES))
    parser.add_argument("--limit", type=int, default=0, help="sinif basina klip siniri (deneme)")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = parser.parse_args()

    root, out_root = Path(args.clips), Path(args.out)
    detector = PoseDetector(args.weights)
    urfd = load_urfd_labels(root / URFD_LABELS)
    print(f"{'sinif':8} {'klip':>5} {'ornek':>9} {'iz':>6} {'izsiz klip':>11}")
    for name in [c.strip().upper() for c in args.classes.split(",") if c.strip()]:
        clips = sorted((root / name).glob("*.mp4"))
        if args.limit:
            clips = clips[:args.limit]
        out_dir = out_root / name
        out_dir.mkdir(parents=True, exist_ok=True)
        samples = tracks = empty = 0
        for clip in clips:
            target = out_dir / (clip.stem + ".npz")
            if target.exists():
                with np.load(target) as old:
                    frame, track = old["frame"], old["track"]
            else:
                fps, n_frames, per_track = clip_tracks(clip, detector)
                events = urfd.get(clip.stem) if name == "FALL" else None
                data = pack(fps, n_frames, per_track, events)
                # Once gecici dosyaya, sonra tek adimda yerine: yarida kesilen
                # kosu bozuk npz birakiyordu ve devam eden kosu onu atliyordu.
                tmp = target.with_suffix(".tmp")
                with open(tmp, "wb") as fh:
                    np.savez_compressed(fh, **data)
                os.replace(tmp, target)
                frame, track = data["frame"], data["track"]
            samples += len(frame)
            tracks += len(np.unique(track))
            empty += 0 if len(frame) else 1
        print(f"{name:8} {len(clips):5d} {samples:9d} {tracks:6d} {empty:11d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
