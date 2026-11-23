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

Asama 13.3a: kare hizi taramasi. `--fps 0,10,5 --drop regular,jitter --seeds 0,1,2
--out logs/x.json`; iki sonucu `--compare a.json b.json` yan yana basar.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

from eval.pilot_eval import TOLERANCE_SEC, load_annotation, score, to_second_set
from models.tcn import CLASSES, FrameDropper, TCNClassifier
from stream.filters import session_passes
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
TYPES = ("FALL", "RUN", "FIGHT", "ZONE_VIOLATION", "LOITERING")
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


def run_clip(path: Path, detector: PoseDetector, engine,
             dropper: FrameDropper | None = None) -> tuple[list[Candidate], int, float]:
    """Hatti bastan sona kosar (vision/run.py ile ayni sira).

    Dropper False derse kare algilanmadan atlanir: izleyici canlidaki gibi yalniz
    tutulan kareleri gorur. ts (sahne zamani) degismez. Doner: (adaylar,
    tutulan kare, klip suresi sn).
    """
    preprocess, smoother, features = Preprocessor(), Smoother(), FeatureEngine()
    tracker = Tracker(device=detector.device)
    candidates: list[Candidate] = []
    kept = seen = 0
    with VideoSource(str(path)) as source:
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():
                    break
                continue
            seen += 1
            ts = frame.idx / source.fps
            if dropper is not None and not dropper(ts):
                continue
            kept += 1
            image = preprocess(frame.image)
            tracks = smoother(tracker.update(detector([image])[0], image, ts), ts)
            windows = features(tracks, frame.idx, ts, image.shape[:2])
            candidates.extend(engine(windows))
        fps = source.fps
    return candidates, kept, seen / fps if fps else 0.0


def holdout_clips(train_root: Path, tracks_root: Path, limit: int) -> list[tuple[Path, str]]:
    """Egitimde kullanilmayan klipler — bolme kurali models/tcn.py ile ayni."""
    out: list[tuple[Path, str]] = []
    for name in CLASSES:
        files = sorted((tracks_root / name).glob("*.npz"))
        picked = [f for i, f in enumerate(files) if i % VAL_EVERY == 0]
        if limit:
            picked = picked[:limit]
        for npz in picked:
            clip = train_root / name / (npz.stem + ".mp4")
            if clip.exists():
                out.append((clip, name))
    return out


def session_filter(candidates: list[Candidate], gap_sec: float = 3.0,
                   min_hits: int = 2) -> list[Candidate]:
    """Spark'in onundeki gercek suzgec: (iz anahtari, tip) basina sahne
    zamaninda oturumlara bol, session_passes gecen oturumlarin adaylarini tut."""
    groups: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for c in candidates:
        key = "-".join(str(t) for t in sorted(c.track_ids))
        groups[(key, c.anomaly_type)].append(c)
    kept: list[Candidate] = []
    for (_, anomaly), cands in groups.items():
        cands.sort(key=lambda c: c.ts)
        session = [cands[0]]
        for c in cands[1:] + [None]:
            if c is not None and c.ts - session[-1].ts < gap_sec:
                session.append(c)
                continue
            if session_passes(len(session), session[-1].ts - session[0].ts,
                              anomaly, min_hits):
                kept.extend(session)
            session = [c]
    return kept


def expand_configs(fps_list: list[float], drops: list[str],
                   seeds: list[int]) -> list[tuple[float, str, int]]:
    """(fps, drop, seed): 0 -> tek 'native' satir; jitter -> tohum basina satir."""
    out: list[tuple[float, str, int]] = []
    for fps in fps_list:
        if fps == 0:
            out.append((0.0, "native", 0))
            continue
        for drop in drops:
            if drop == "jitter":
                out.extend((fps, drop, s) for s in seeds)
            else:
                out.append((fps, drop, 0))
    return out


def score_holdout(cands: list[Candidate], label: str, tp, fp, fn) -> None:
    found = {c.anomaly_type for c in cands}
    if label == "NORMAL":
        for anomaly in found:            # NORMAL klipte her aday yanlis pozitif
            fp[anomaly] += 1
        return
    if label in found:
        tp[label] += 1
    else:
        fn[label] += 1
    for anomaly in found - {label}:
        fp[anomaly] += 1


def _counts(tp, fp, fn) -> dict[str, dict[str, int]]:
    return {t: {"tp": tp.get(t, 0), "fp": fp.get(t, 0), "fn": fn.get(t, 0)}
            for t in sorted(set(tp) | set(fp) | set(fn))}


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return prec, rec, 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0


def totals(counts: dict[str, dict[str, int]]) -> tuple[float, float, float]:
    """Mikro toplam (markdown_table TOPLAM satiri ile ayni)."""
    return prf(*(sum(v[k] for v in counts.values()) for k in ("tp", "fp", "fn")))


def type_f1(counts: dict[str, dict[str, int]], t: str) -> float:
    v = counts.get(t)
    return prf(v["tp"], v["fp"], v["fn"])[2] if v else 0.0


def eff_fps(clips: dict[str, dict]) -> float:
    dur = sum(c["duration"] for c in clips.values())
    return sum(c["kept"] for c in clips.values()) / dur if dur else 0.0


def _row(mode, set_name, cfg, raw, filt, clips) -> dict:
    fps, drop, seed = cfg
    return {"mode": mode, "set": set_name, "fps": fps, "drop": drop, "seed": seed,
            "eff_fps": round(eff_fps(clips), 3),
            "raw": _counts(*raw), "filtered": _counts(*filt), "clips": clips}


def _new() -> tuple[dict, dict, dict]:
    return defaultdict(int), defaultdict(int), defaultdict(int)


def _dropper(cfg, clip: Path) -> FrameDropper | None:
    fps, drop, seed = cfg
    if fps == 0:
        return None
    # klip basina tohum: sonuc klip sirasindan bagimsiz ve tekrarlanabilir
    return FrameDropper(fps, drop, seed + zlib.crc32(clip.stem.encode()))


def _info(cands, kept, duration) -> dict:
    by_type: dict[str, int] = defaultdict(int)
    for c in cands:
        by_type[c.anomaly_type] += 1
    return {"kept": kept, "duration": round(duration, 3), "raw_by_type": dict(by_type)}


def eval_pilot(clips: list[Path], detector, zones_path: str, mode: str, classifier,
               min_conf: float, annotations: Path, cfg) -> dict:
    raw, filt, info = _new(), _new(), {}
    for clip in clips:
        zones = load_zones(zones_path, clip.stem) if zones_path else []
        cands, kept, dur = run_clip(
            clip, detector, build_engine(mode, zones, classifier, min_conf),
            _dropper(cfg, clip))
        info[clip.stem] = _info(cands, kept, dur)
        ann = annotations / f"{clip.stem}.json"
        if not ann.exists():              # etiketsiz: yalniz ham sayi raporlanir
            continue
        events, eval_end = load_annotation(ann)
        for acc, group in ((raw, cands), (filt, session_filter(cands))):
            cand_set = to_second_set(group)
            if eval_end is not None:
                cand_set = {c for c in cand_set if c[1] < eval_end}
            score(cand_set, events, TOLERANCE_SEC, *acc)
    return _row(mode, "pilot", cfg, raw, filt, info)


def eval_holdout(clips: list[tuple[Path, str]], detector, mode: str, classifier,
                 min_conf: float, cfg) -> dict:
    raw, filt, info = _new(), _new(), {}
    for clip, label in clips:
        cands, kept, dur = run_clip(
            clip, detector, build_engine(mode, [], classifier, min_conf),
            _dropper(cfg, clip))
        info[clip.stem] = _info(cands, kept, dur)
        score_holdout(cands, label, *raw)
        score_holdout(session_filter(cands), label, *filt)
    return _row(mode, "holdout", cfg, raw, filt, info)


def _f(x: float) -> str:
    return f"{x:.2f}"


def summary_table(rows: list[dict]) -> str:
    lines = ["| mode | set | fps | drop | seed | eff_fps | raw P | raw R | raw F1 | "
             "filt P | filt R | filt F1 | " + " | ".join(f"raw F1 {t}" for t in TYPES) + " |",
             "|" + "---|" * (12 + len(TYPES))]
    for r in rows:
        rp, rr, rf = totals(r["raw"])
        fp_, fr, ff = totals(r["filtered"])
        lines.append(
            f"| {r['mode']} | {r['set']} | {r['fps']:g} | {r['drop']} | {r['seed']} | "
            f"{r['eff_fps']:.1f} | {_f(rp)} | {_f(rr)} | {_f(rf)} | {_f(fp_)} | "
            f"{_f(fr)} | {_f(ff)} | "
            + " | ".join(_f(type_f1(r["raw"], t)) for t in TYPES) + " |")
    return "\n".join(lines)


def unannotated_report(rows: list[dict], annotations: Path) -> str:
    lines = []
    for r in rows:
        if r["set"] != "pilot":
            continue
        for stem, c in r["clips"].items():
            if not (annotations / f"{stem}.json").exists():
                lines.append(f"  {r['mode']} fps={r['fps']:g} {r['drop']} seed={r['seed']} "
                             f"{stem}: {c['raw_by_type'] or 'aday yok'}")
    return "\n".join(lines)


def _agg(vals: list[float]) -> str:
    if len(vals) == 1:
        return _f(vals[0])
    return f"{_f(sum(vals) / len(vals))} [{_f(min(vals))}, {_f(max(vals))}]"


def _group(rows: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        out[(r["mode"], r["set"], r["fps"], r["drop"])].append(r)
    return out


def _cell(rs: list[dict] | None, pick) -> str:
    return _agg([pick(r) for r in rs]) if rs else "-"


def compare_table(a: dict, b: dict) -> str:
    """Iki sonuc dosyasini (mode, set, fps, drop) anahtariyla yan yana basar;
    ayni anahtarin birden cok tohumu varsa ortalama [min, maks] verilir."""
    ga, gb = _group(a["rows"]), _group(b["rows"])
    lines = []
    if a["meta"].get("holdout") != b["meta"].get("holdout"):
        lines.append("UYARI: holdout klip listeleri iki dosyada farkli")
    lines += ["| mode | set | fps | drop | raw F1 A -> B | filt F1 A -> B | "
              "per-type raw F1 A -> B |", "|---|---|---|---|---|---|---|"]
    raw_f1 = lambda r: totals(r["raw"])[2]
    filt_f1 = lambda r: totals(r["filtered"])[2]
    for key in sorted(set(ga) | set(gb), key=lambda k: (k[0], k[1], -k[2], k[3])):
        mode, set_name, fps, drop = key
        cells = [f"{_cell(ga.get(key), p)} -> {_cell(gb.get(key), p)}"
                 for p in (raw_f1, filt_f1)]
        types = " ".join(
            f"{t}:{_cell(ga.get(key), lambda r, t=t: type_f1(r['raw'], t))}"
            f"->{_cell(gb.get(key), lambda r, t=t: type_f1(r['raw'], t))}" for t in TYPES)
        lines.append(f"| {mode} | {set_name} | {fps:g} | {drop} | {cells[0]} | "
                     f"{cells[1]} | {types} |")
    return "\n".join(lines)


def _csv(text: str, cast) -> list:
    return [cast(x.strip()) for x in text.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Kural / model / hibrit ablation")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--annotations", default="eval/annotations")
    parser.add_argument("--train", default="data/train")
    parser.add_argument("--tracks", default="data/tracks")
    parser.add_argument("--zones", default="eval/zones.json")
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--min-conf", type=float, default=0.60)
    parser.add_argument("--limit", type=int, default=0, help="holdout sinif basina klip siniri")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    parser.add_argument("--fps", default="0", help="virgullu; 0 = ozgun hiz")
    parser.add_argument("--drop", default="regular", help="regular,jitter")
    parser.add_argument("--seeds", default="0", help="yalniz jitter icin")
    parser.add_argument("--out", default="", help="sonuc json yolu")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = parser.parse_args()

    if args.compare:
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.compare)
        print(compare_table(a, b))
        return 0

    started = time.strftime("%Y-%m-%d %H:%M")
    configs = expand_configs(_csv(args.fps, float), _csv(args.drop, str), _csv(args.seeds, int))
    detector = PoseDetector(args.weights)
    classifier = TCNClassifier(detector.device)
    annotations = Path(args.annotations)
    pilot = sorted(Path(args.clips).glob("*.mp4"))
    holdout = holdout_clips(Path(args.train), Path(args.tracks), args.limit)
    print(f"  pilot {len(pilot)} klip, holdout {len(holdout)} klip, "
          f"tcn_min_conf={args.min_conf}, {len(configs)} yapilandirma\n")

    rows: list[dict] = []
    for mode in _csv(args.modes, str):
        for cfg in configs:
            print(f"  mod={mode} fps={cfg[0]:g} drop={cfg[1]} seed={cfg[2]}", flush=True)
            rows.append(eval_pilot(pilot, detector, args.zones, mode, classifier,
                                   args.min_conf, annotations, cfg))
            rows.append(eval_holdout(holdout, detector, mode, classifier,
                                     args.min_conf, cfg))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        meta = {"argv": sys.argv[1:], "pilot": [p.stem for p in pilot],
                "holdout": [c.stem for c, _ in holdout], "started": started}
        out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=1), encoding="utf-8")
    print("\n" + summary_table(rows))
    extra = unannotated_report(rows, annotations)
    if extra:
        print("\n  etiketsiz pilot klipler (ham aday, puanlanmaz):\n" + extra)
    return 0


if __name__ == "__main__":
    sys.exit(main())
