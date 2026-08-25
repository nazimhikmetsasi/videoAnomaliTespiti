"""Pilot klip degerlendirmesi: Asama 3 onay kriteri (PLAN.md SS6).

Her klip icin hatti (on isleme -> pose -> takip -> duzleme -> oznitelik ->
kural) baslatan kosar, aday olaylari `(tip, saniye)` kumesine indirir ve
`eval/annotations/*.json` gercek referansiyla saniye bazli karsilastirir.
Cikti: tip basina TP/FP/FN/precision/recall/F1 markdown tablosu + klip
basina ham (sifrelenmemis) aday sayisi -- Asama 4'te Spark'in suzecegi
gurultu tabani buradan olculur.

Calistirma:
    venv\\Scripts\\python.exe -m eval.pilot_eval --clips data/pilot --zones eval/zones.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from vision.rules.engine import Candidate, RuleEngine
from vision.run import load_zones
from vision.source import VideoSource
from vision.stages.features import FeatureEngine
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import FRAME_W, Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Tracker

TOLERANCE_SEC = 1.0


def run_clip(path: Path, detector: PoseDetector, zones_path: str,
             max_frames: int = 0) -> list[Candidate]:
    """Tek klip icin hatti bastan sona kosar, ham aday listesini dondurur."""
    zones = load_zones(zones_path, path.stem) if zones_path else []
    preprocess = Preprocessor()
    tracker = Tracker(device=detector.device)
    smoother = Smoother()
    features = FeatureEngine()
    rules = RuleEngine(zones=zones)

    candidates: list[Candidate] = []
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
            candidates.extend(rules(windows))
            frames += 1
            if max_frames and frames >= max_frames:
                break
    return candidates


def to_second_set(candidates: list[Candidate]) -> set[tuple[str, int]]:
    """Adaylari (tip, saniye) kumesine indirir.

    Bir kural kosul suresince HER karede yeni aday uretir; saniyeye
    yuvarlayip kumeye koymak ayni olayi tekrar tekrar TP/FP saymayi onler.
    """
    return {(c.anomaly_type, int(c.ts)) for c in candidates}


def score(cand_set: set[tuple[str, int]], events: list[dict], tol: float,
          tp: dict[str, int], fp: dict[str, int], fn: dict[str, int]) -> None:
    """Bir klibin aday kumesini gercek referans olaylarla karsilastirir.

    Her gercek olay (NORMAL haric) esiginde eslenen en az bir aday varsa TP,
    yoksa FN. Hicbir gercek olaya eslenmeyen aday (NORMAL araliginda uretilen
    dahil) FP'dir.
    """
    matched: set[tuple[str, int]] = set()
    for ev in events:
        if ev["type"] == "NORMAL":
            continue
        lo, hi = ev["start_sec"] - tol, ev["end_sec"] + tol
        hits = {c for c in cand_set if c[0] == ev["type"] and lo <= c[1] <= hi}
        if hits:
            tp[ev["type"]] += 1
            matched |= hits
        else:
            fn[ev["type"]] += 1
    for c in cand_set - matched:
        fp[c[0]] += 1


def markdown_table(tp: dict[str, int], fp: dict[str, int], fn: dict[str, int]) -> str:
    types = sorted(set(tp) | set(fp) | set(fn))
    lines = ["| tip | TP | FP | FN | precision | recall | F1 |",
             "|---|---|---|---|---|---|---|"]
    tot = {"tp": 0, "fp": 0, "fn": 0}
    for t in types:
        a, b, c = tp.get(t, 0), fp.get(t, 0), fn.get(t, 0)
        tot["tp"] += a
        tot["fp"] += b
        tot["fn"] += c
        prec = a / (a + b) if (a + b) else 0.0
        rec = a / (a + c) if (a + c) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        lines.append(f"| {t} | {a} | {b} | {c} | {prec:.2f} | {rec:.2f} | {f1:.2f} |")
    a, b, c = tot["tp"], tot["fp"], tot["fn"]
    prec = a / (a + b) if (a + b) else 0.0
    rec = a / (a + c) if (a + c) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    lines.append(f"| **TOPLAM** | {a} | {b} | {c} | {prec:.2f} | {rec:.2f} | {f1:.2f} |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Asama 3 pilot degerlendirme")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--annotations", default="eval/annotations")
    parser.add_argument("--zones", default="eval/zones.json")
    parser.add_argument("--tolerance-sec", type=float, default=TOLERANCE_SEC)
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

    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    raw_counts: dict[str, int] = {}
    unlabeled: list[str] = []

    for clip in clip_paths:
        print(f"  kosuluyor: {clip.name}")
        candidates = run_clip(clip, detector, args.zones, args.max_frames)
        raw_counts[clip.stem] = len(candidates)

        ann_path = ann_dir / f"{clip.stem}.json"
        if not ann_path.exists():
            unlabeled.append(clip.stem)
            continue

        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        events, cand_set = ann["events"], to_second_set(candidates)
        eval_end = ann.get("eval_end_sec")
        if eval_end is not None:
            # SS10.4: bolge kameraya bagli bir kavramdir (zone_01 28. sn'de
            # sahne degistiriyor). eval_end_sec'ten sonrasi hem referans hem
            # adaylardan cikarilir; alan yoksa davranis degismez.
            events = [e for e in events if e["start_sec"] < eval_end]
            cand_set = {c for c in cand_set if c[1] < eval_end}
        score(cand_set, events, args.tolerance_sec, tp, fp, fn)

    detector.close()

    print("\n" + "=" * 62)
    print("ASAMA 3 - PILOT DEGERLENDIRME")
    print("=" * 62 + "\n")
    print(markdown_table(tp, fp, fn))

    print("\n  ham aday sayisi (klip basina, saniyeye indirgenmemis):")
    for stem, n in raw_counts.items():
        print(f"    {stem:<16} {n}")

    if unlabeled:
        print("\n  etiketsiz (degerlendirme disi): " + ", ".join(unlabeled))
    return 0


if __name__ == "__main__":
    sys.exit(main())
