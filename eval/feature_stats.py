"""SS10.5 olcum yardimcisi: klip basina oznitelik tepe tablosu + esik secimi.

FALL ve RUN ilk pilot kosusunda hic tetiklemedi (ASAMA3_PLAN.md SS10); kok
neden oznitelik tanimlarindaydi, kural kodu degil. Bu script duzeltmelerin
kanitini olcup basar -- run_norm_speed ve run_gait_speed TAHMINLE degil
NORMAL/olay dagilimlarindan turetilir, Asama 2.1'de pose_conf'un 0.35'ten
0.25'e ayni yontemle cekilmesiyle aynidir.

Calistirma:
    venv\\Scripts\\python.exe -m eval.feature_stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from vision.rules.engine import Thresholds
from vision.source import VideoSource
from vision.stages.features import FeatureEngine, FrameFeatures
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import FRAME_W, Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Tracker

STEP = 0.05        # esik yuvarlama adimi (SS10.5#2)
MIN_SAMPLES = 5     # bundan az kareyle yuzdelik guvenilmez, varsayilan korunur


def run_clip_features(path: Path, detector: PoseDetector,
                       max_frames: int = 0) -> list[tuple[float, FrameFeatures]]:
    """Klibi bastan sona kosar, HER pozlu izin her karedeki oznitelik degerini dondurur."""
    preprocess = Preprocessor()
    tracker = Tracker(device=detector.device)
    smoother = Smoother()
    features = FeatureEngine()

    rows: list[tuple[float, FrameFeatures]] = []
    frames = 0
    with VideoSource(str(path)) as source:
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():
                    break
                continue
            image = preprocess(frame.image)
            result = detector([image])[0]
            tracks = tracker.update(result, image)
            ts = frame.idx / source.fps
            tracks = smoother(tracks, ts)
            windows = features(tracks, frame.idx, ts, image.shape[:2])
            for window in windows.values():
                if window.last.has_pose:
                    rows.append((ts, window.last))
            frames += 1
            if max_frames and frames >= max_frames:
                break
    return rows


def _label(events: list[dict], ts: float) -> str | None:
    """ts'nin dustugu gercek referans araligin tipi; hicbirine dusmezse None."""
    for ev in events:
        if ev["start_sec"] <= ts <= ev["end_sec"]:
            return ev["type"]
    return None


def _round_step(x: float, step: float = STEP) -> float:
    return round(round(x / step) * step, 2)


def _peak_row(feats: list[FrameFeatures]) -> str:
    tilt = max(f.body_tilt for f in feats)
    vy = max(f.norm_vy for f in feats)
    speed = max(f.norm_speed for f in feats)
    limb = float(np.median([f.limb_speed for f in feats]))
    return f"{tilt:>10.1f} {vy:>9.2f} {speed:>11.2f} {limb:>12.2f}  ({len(feats)} kare)"


def print_peak_table(clip_rows: dict[str, dict[str, list[FrameFeatures]]]) -> None:
    print(f"\n  {'klip':<12} {'aralik':<16} {'body_tilt':>10} {'norm_vy':>9} "
          f"{'norm_speed':>11} {'limb_speed':>13}")
    print(f"  {'':<12} {'':<16} {'tepe':>10} {'tepe':>9} {'tepe':>11} {'medyan':>13}")
    for clip, by_label in clip_rows.items():
        for label, feats in by_label.items():
            if not feats:
                continue
            print(f"  {clip:<12} {label:<16} {_peak_row(feats)}")


def _percentile_report(name: str, normal: list[float], event: list[float],
                        current_default: float) -> float:
    """SS10.5#2: esik = NORMAL 90. yuzdelik ile olay 10. yuzdeliginin ortasi,
    0.05 adimina yuvarlanir. Dagilimlar ortusuyorsa (p90 >= p10) esik konmaz --
    tahminle uydurulmaz, varsayilan korunur ve ortusme raporlanir."""
    if len(normal) < MIN_SAMPLES or len(event) < MIN_SAMPLES:
        print(f"  {name}: yetersiz ornek (normal={len(normal)}, olay={len(event)}), "
              f"varsayilan {current_default} korunuyor")
        return current_default
    p90 = float(np.percentile(normal, 90))
    p10 = float(np.percentile(event, 10))
    print(f"  {name}: NORMAL p90={p90:.3f} (n={len(normal)}), "
          f"olay p10={p10:.3f} (n={len(event)})")
    if p90 >= p10:
        print(f"  {name}: dagilimlar ortusuyor (p90 >= p10) -- esik konmuyor, "
              f"varsayilan {current_default} korunuyor")
        return current_default
    mid = (p90 + p10) / 2
    threshold = _round_step(mid)
    print(f"  {name}: esik = round(({p90:.3f} + {p10:.3f}) / 2, 0.05 adim) = {threshold}")
    return threshold


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SS10.5 oznitelik olcumu")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--annotations", default="eval/annotations")
    parser.add_argument("--max-frames", type=int, default=0, help="0 = sinirsiz")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    clips_dir, ann_dir = Path(args.clips), Path(args.annotations)
    clip_paths = sorted(clips_dir.glob("*.mp4"))
    if not clip_paths:
        print(f"  HATA: {clips_dir} icinde klip yok")
        return 1

    detector = PoseDetector(DEFAULT_WEIGHTS, device="cuda", conf=0.25, imgsz=FRAME_W)

    clip_rows: dict[str, dict[str, list[FrameFeatures]]] = {}
    normal_speed: list[float] = []
    normal_gait: list[float] = []
    run_speed: list[float] = []
    run_gait: list[float] = []

    for clip in clip_paths:
        print(f"  kosuluyor: {clip.name}")
        rows = run_clip_features(clip, detector, args.max_frames)

        ann_path = ann_dir / f"{clip.stem}.json"
        if not ann_path.exists():
            # police_run: etiket yok -- raw satir olarak gorunur, NORMAL/olay
            # ayrimina (ve dolayisiyla esik olcumune) girmez.
            clip_rows[clip.stem] = {"(etiketsiz)": [f for _, f in rows]}
            continue

        events = json.loads(ann_path.read_text(encoding="utf-8"))["events"]
        by_label: dict[str, list[FrameFeatures]] = {}
        for ts, feat in rows:
            label = _label(events, ts)
            if label is None:
                continue
            by_label.setdefault(label, []).append(feat)
        clip_rows[clip.stem] = by_label

        for feat in by_label.get("NORMAL", []):
            normal_speed.append(feat.norm_speed)
            normal_gait.append(feat.limb_speed)
        for feat in by_label.get("RUN", []):
            run_speed.append(feat.norm_speed)
            run_gait.append(feat.limb_speed)

    detector.close()

    print("\n" + "=" * 72)
    print("SS10.5#1 - KLIP BASINA OZNITELIK TEPE TABLOSU (NORMAL vs olay)")
    print("=" * 72)
    print_peak_table(clip_rows)

    print("\n" + "=" * 72)
    print("SS10.5#2 - RUN ESIK SECIMI")
    print("=" * 72)
    default = Thresholds()
    run_norm_speed = _percentile_report("run_norm_speed", normal_speed, run_speed,
                                         default.run_norm_speed)
    run_gait_speed = _percentile_report("run_gait_speed", normal_gait, run_gait,
                                         default.run_gait_speed)
    print(f"\n  onerilen: run_norm_speed={run_norm_speed}, run_gait_speed={run_gait_speed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
