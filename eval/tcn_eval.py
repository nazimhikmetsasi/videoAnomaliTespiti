"""Asama 9.5 onay kriteri: kural / model / hibrit ablation tablosu.

Iki kume ayri ayri olculur ve TEK ortalama verilmez:

1. **Pilot klipler** (`eval/annotations/*.json`) — uretim alani, 1080p,
   saniye bazli gercek referans. `eval/pilot_eval.py` ile ayni karsilastirma.
2. **Holdout klipler** (`data/train/<SINIF>/`) — egitimde KULLANILMAYAN
   klipler; bolme `models/tcn.load_split` ile birebir ayni kurala gore
   (sirali listede her 5. klip). Metrik klip bazlidir: klibin etiketi
   adaylar arasinda geciyorsa TP.

Alan farki bu iki tablonun arasindaki farkta gorunur; ortalama alinsa
gorunmezdi.

    venv/Scripts/python.exe -m eval.tcn_eval --zones eval/zones.json
    venv/Scripts/python.exe -m eval.tcn_eval --modes rule,hybrid --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from eval.pilot_eval import TOLERANCE_SEC, markdown_table, score, to_second_set
from models.tcn import CLASSES, TCNClassifier
from vision.rules.arbiter import HybridArbiter
from vision.rules.engine import Candidate, RuleEngine
from vision.run import load_zones
from vision.source import VideoSource
from vision.stages.features import FeatureEngine
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Tracker

MODES = ("rule", "model", "hybrid")
VAL_EVERY = 5      # models/tcn.py VAL_EVERY ile AYNI olmali (sizinti kontrolu)


class NoRules:
    """Kural motorunun yuzeyi, adaylari yok. `model` modu icin.

    Ayri bir hakem sinifi yazmak yerine kural motorunu susturmak, olculen
    seyin gercekten AYNI hakem oldugunu garantiler.
    """

    def __init__(self, engine: RuleEngine) -> None:
        self._engine = engine

    def __call__(self, windows) -> list[Candidate]:
        return []

    @property
    def thresholds(self):
        return self._engine.thresholds

    @property
    def zones(self):
        return self._engine.zones


def build_engine(mode: str, zones, classifier, min_conf: float):
    rules = RuleEngine(zones=zones)
    if mode == "rule":
        return HybridArbiter(rules, None)
    if mode == "model":
        return HybridArbiter(NoRules(rules), classifier, min_conf=min_conf)
    return HybridArbiter(rules, classifier, min_conf=min_conf)


def run_clip(path: Path, detector: PoseDetector, engine) -> list[Candidate]:
    """Hatti bastan sona kosar (vision/run.py ile ayni sira)."""
    preprocess, smoother, features = Preprocessor(), Smoother(), FeatureEngine()
    tracker = Tracker(device=detector.device)
    candidates: list[Candidate] = []
    with VideoSource(str(path)) as source:
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():
                    break
                continue
            image = preprocess(frame.image)
            tracks = smoother(tracker.update(detector([image])[0], image),
                              frame.idx / source.fps)
            windows = features(tracks, frame.idx, frame.idx / source.fps, image.shape[:2])
            candidates.extend(engine(windows))
    return candidates


def holdout_clips(train_root: Path, sequences_root: Path, limit: int) -> list[tuple[Path, str]]:
    """Egitimde kullanilmayan klipler — bolme kurali models/tcn.py ile ayni."""
    out: list[tuple[Path, str]] = []
    for name in CLASSES:
        files = sorted((sequences_root / name).glob("*.npz"))
        picked = [f for i, f in enumerate(files) if i % VAL_EVERY == 0]
        if limit:
            picked = picked[:limit]
        for npz in picked:
            clip = train_root / name / (npz.stem + ".mp4")
            if clip.exists():
                out.append((clip, name))
    return out


def eval_pilot(clips: list[Path], detector, zones_path: str, mode: str,
               classifier, min_conf: float, annotations: Path) -> str:
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    for clip in clips:
        events = json.loads((annotations / f"{clip.stem}.json").read_text(
            encoding="utf-8"))["events"]
        zones = load_zones(zones_path, clip.stem) if zones_path else []
        cands = run_clip(clip, detector, build_engine(mode, zones, classifier, min_conf))
        score(to_second_set(cands), events, TOLERANCE_SEC, tp, fp, fn)
    return markdown_table(tp, fp, fn)


def eval_holdout(clips: list[tuple[Path, str]], detector, mode: str,
                 classifier, min_conf: float) -> str:
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    for clip, label in clips:
        cands = run_clip(clip, detector, build_engine(mode, [], classifier, min_conf))
        found = {c.anomaly_type for c in cands}
        if label == "NORMAL":
            for anomaly in found:        # NORMAL klipte her aday yanlis pozitif
                fp[anomaly] += 1
            continue
        if label in found:
            tp[label] += 1
        else:
            fn[label] += 1
        for anomaly in found - {label}:
            fp[anomaly] += 1
    return markdown_table(tp, fp, fn)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kural / model / hibrit ablation")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--annotations", default="eval/annotations")
    parser.add_argument("--train", default="data/train")
    parser.add_argument("--sequences", default="data/sequences")
    parser.add_argument("--zones", default="eval/zones.json")
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--min-conf", type=float, default=0.60)
    parser.add_argument("--limit", type=int, default=0, help="holdout sinif basina klip siniri")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = parser.parse_args()

    detector = PoseDetector(args.weights)
    classifier = TCNClassifier(detector.device)
    annotations = Path(args.annotations)
    pilot = sorted(p for p in Path(args.clips).glob("*.mp4")
                   if (annotations / f"{p.stem}.json").exists())
    holdout = holdout_clips(Path(args.train), Path(args.sequences), args.limit)
    print(f"  pilot {len(pilot)} klip, holdout {len(holdout)} klip, "
          f"tcn_min_conf={args.min_conf}\n")

    for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
        print(f"\n## Mod: {mode}\n\n### Pilot klipler (uretim alani)\n")
        print(eval_pilot(pilot, detector, args.zones, mode, classifier,
                         args.min_conf, annotations))
        print(f"\n### Holdout klipler (egitim disi)\n")
        print(eval_holdout(holdout, detector, mode, classifier, args.min_conf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
