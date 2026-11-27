"""Saha degerlendirmesi (Asama 14A, ASAMA14_PLAN.md SS3).

Her klip canli hatla AYNI yoldan gecer: `vision.run`'in `CameraPipeline`'i
(kural + hakem + RUN_ZONE cevirisi + dusme sonrasi izleyici), gercek zamanli
degil, Kafka / WS / kanit kapali. Cikti: tip puani (ham ve Spark suzgeci
sonrasi), dusme sonucu tablosu (beklenen x bulunan), markdown + JSON.

    venv\\Scripts\\python.exe -m eval.field_eval --clips data/pilot --annotations eval/annotations --zones eval/zones.json --out logs/field_pilot.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from eval.pilot_eval import TOLERANCE_SEC, load_annotation, markdown_table, score, to_second_set
from eval.tcn_eval import session_filter

FOUND = ("down", "recovered", "unknown", "none")


def load_events(path: Path) -> tuple[list[dict], float | None, int]:
    """Etiket + atlanan (saniyesi null) olay sayisi.

    `load_annotation` null saniyede (eval_end_sec varken) patlar; bu yuzden
    doldurulmamis olaylar once ayiklanip gecici bir kopya ile okunur.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    kept = [e for e in raw["events"]
            if e.get("start_sec") is not None and e.get("end_sec") is not None]
    skipped = len(raw["events"]) - len(kept)
    if skipped == 0:
        events, eval_end = load_annotation(path)
        return events, eval_end, 0
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / path.name
        tmp.write_text(json.dumps({**raw, "events": kept}), encoding="utf-8")
        events, eval_end = load_annotation(tmp)
    return events, eval_end, skipped


def match_outcomes(events: list[dict], outcomes: list, tol: float
                   ) -> tuple[list[dict], list]:
    """`outcome` alanli her FALL etiketini, inis zamani [start-tol, end+tol]
    icinde olan sonuca esler (birden cok ise pencere merkezine en yakin).
    Doner: (satirlar, eslesmeyen sonuclar)."""
    rows: list[dict] = []
    used: set[int] = set()
    for ev in events:
        if ev.get("type") != "FALL" or not ev.get("outcome"):
            continue
        lo, hi = ev["start_sec"] - tol, ev["end_sec"] + tol
        mid = (ev["start_sec"] + ev["end_sec"]) / 2
        hits = [i for i, o in enumerate(outcomes) if lo <= o.fall_ts <= hi]
        row = {"start_sec": ev["start_sec"], "end_sec": ev["end_sec"],
               "expected": ev["outcome"], "found": "none", "decided_after_sec": None}
        if hits:
            best = min(hits, key=lambda i: abs(outcomes[i].fall_ts - mid))
            used.add(best)
            o = outcomes[best]
            row["found"] = o.outcome
            row["decided_after_sec"] = o.metrics.get("decided_after_sec")
        rows.append(row)
    return rows, [o for i, o in enumerate(outcomes) if i not in used]


def confusion_table(rows: list[dict]) -> str:
    exp = sorted({r["expected"] for r in rows})
    lines = ["| beklenen \\ bulunan | " + " | ".join(FOUND) + " |",
             "|---|" + "---|" * len(FOUND)]
    for e in exp:
        cells = [str(sum(1 for r in rows if r["expected"] == e and r["found"] == f))
                 for f in FOUND]
        lines.append(f"| {e} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_clip(pipe, detector) -> None:
    """vision.run.main'in tek kaynak dongusu. main() fonksiyon olarak
    yeniden kullanilamiyor (detektoru kendi kurup rapor basiyor), bu yuzden
    ayni cagri sirasi (read -> prepare -> detector -> consume) burada."""
    while not pipe.finished:
        frame = pipe.read(timeout=2.0)
        if frame is None:
            continue
        image = pipe.prepare(frame)
        result = detector([image])[0]
        pipe.consume(frame, image, result, 0.0)
        if pipe.args.max_frames and pipe.frames >= pipe.args.max_frames:
            break


def _counts(tp, fp, fn) -> dict[str, dict[str, int]]:
    return {t: {"tp": tp.get(t, 0), "fp": fp.get(t, 0), "fn": fn.get(t, 0)}
            for t in sorted(set(tp) | set(fp) | set(fn))}


def score_clip(cands: list, events: list[dict], eval_end: float | None, tol: float,
               raw_acc: tuple, filt_acc: tuple) -> None:
    """Ham ve Spark suzgeci sonrasi puanlari ortak toplayicilara ekler."""
    for acc, group in ((raw_acc, cands), (filt_acc, session_filter(cands))):
        cand_set = to_second_set(group)
        if eval_end is not None:
            cand_set = {c for c in cand_set if c[1] < eval_end}
        score(cand_set, events, tol, *acc)


def _new() -> tuple[dict, dict, dict]:
    return defaultdict(int), defaultdict(int), defaultdict(int)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Asama 14A saha degerlendirmesi")
    p.add_argument("--clips", default="data/field")
    p.add_argument("--annotations", default="eval/annotations/field")
    p.add_argument("--zones", default="")
    p.add_argument("--postfall-sec", type=float, default=25.0)
    p.add_argument("--no-tcn", action="store_true")
    p.add_argument("--no-clahe", action="store_true")
    p.add_argument("--tolerance-sec", type=float, default=TOLERANCE_SEC)
    p.add_argument("--out", default="")
    p.add_argument("--max-frames", type=int, default=0, help="0 = sinirsiz")
    return p.parse_args(argv)


def pipeline_args(clip: Path, a: argparse.Namespace):
    """Hat argumanlari: kurallar acik, gercek zamanli degil, Kafka/WS/kanit yok."""
    from vision.run import parse_args as run_args
    argv = ["--source", str(clip), "--rules", "--postfall-sec", str(a.postfall_sec),
            "--max-frames", str(a.max_frames), "--heartbeat-sec", "0"]
    if a.zones:
        argv += ["--zones", a.zones]
    if a.no_tcn:
        argv.append("--no-tcn")
    if a.no_clahe:
        argv.append("--no-clahe")
    return run_args(argv)


def _fmt_s(x) -> str:
    return "-" if x is None else f"{x:.1f}"


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    clips_dir, ann_dir = Path(a.clips), Path(a.annotations)
    clips = sorted(clips_dir.rglob("*.mp4"))
    if not clips:
        print(f"  HATA: {clips_dir} icinde klip yok")
        return 1

    from vision.camera import CameraPipeline
    from vision.run import choose_reid
    from vision.stages.pose_detector import PoseDetector

    base = pipeline_args(clips[0], a)
    detector = PoseDetector(base.model, device=base.device, conf=base.conf,
                            imgsz=base.imgsz, reid_feats=not base.no_reid)
    reid_model, _ = choose_reid(base.reid_model, base.no_reid, detector.has_reid_feats)

    raw_acc, filt_acc = _new(), _new()
    all_rows: list[dict] = []
    out_clips: dict[str, dict] = {}
    summary: list[str] = ["| klip | kare | aday | olay | sonuc | not |", "|---|---|---|---|---|---|"]
    unlabeled: list[str] = []
    unmatched_all: list[str] = []

    for clip in clips:
        print(f"  kosuluyor: {clip.name}", flush=True)
        pipe = CameraPipeline(str(clip), pipeline_args(clip, a), reid_model=reid_model)
        pipe.start()
        run_clip(pipe, detector)
        pipe.close()
        cands, outcomes = pipe.all_candidates, pipe.all_outcomes

        entry = {
            "frames": pipe.frames,
            "candidates": [[c.anomaly_type, round(c.ts, 3), list(c.track_ids), c.decided_by]
                           for c in cands],
            "outcomes": [{"track_id": o.track_id, "fall_ts": o.fall_ts, "outcome": o.outcome,
                          "adopted": o.adopted, "metrics": o.metrics} for o in outcomes],
        }
        out_clips[clip.stem] = entry
        ann = ann_dir / f"{clip.stem}.json"
        if not ann.exists():
            unlabeled.append(clip.stem)
            summary.append(f"| {clip.stem} | {pipe.frames} | {len(cands)} | - | - | etiket yok |")
            continue

        events, eval_end, skipped = load_events(ann)
        note = ""
        if skipped:
            note = f"{skipped} olay saniyesiz, atlandi"
            print(f"  UYARI: {clip.stem}: {note}")
        score_clip(cands, events, eval_end, a.tolerance_sec, raw_acc, filt_acc)
        rows, unmatched = match_outcomes(events, outcomes, a.tolerance_sec)
        all_rows += rows
        unmatched_all += [f"{clip.stem}: iz {o.track_id} {o.outcome} inis {o.fall_ts:.1f} sn"
                          for o in unmatched]
        entry["fall_outcomes"] = rows
        entry["unmatched_outcomes"] = [o.track_id for o in unmatched]
        entry["skipped_events"] = skipped
        res = ", ".join(f"{r['expected']}->{r['found']}" for r in rows) or "-"
        summary.append(f"| {clip.stem} | {pipe.frames} | {len(cands)} | {len(events)} | {res} | {note} |")

    detector.close()

    out_md = ["=" * 62, "ASAMA 14A - SAHA DEGERLENDIRME", "=" * 62, "",
              "\n".join(summary), "",
              "Tip puani (ham adaylar):", markdown_table(*raw_acc), "",
              "Tip puani (Spark suzgeci sonrasi):", markdown_table(*filt_acc), ""]
    if all_rows:
        out_md += ["Dusme sonucu (beklenen x bulunan):", confusion_table(all_rows), "",
                   "Karar sureleri: " + ", ".join(
                       f"{r['expected']}->{r['found']} {_fmt_s(r['decided_after_sec'])} sn"
                       for r in all_rows), ""]
    if unmatched_all:
        out_md += ["Eslesmeyen sonuclar:"] + [f"  {u}" for u in unmatched_all] + [""]
    if unlabeled:
        out_md.append("Etiketsiz (puan disi): " + ", ".join(unlabeled))
    print("\n" + "\n".join(out_md))

    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "argv": sys.argv[1:] if argv is None else argv,
            "tolerance_sec": a.tolerance_sec,
            "scores": {"raw": _counts(*raw_acc), "filtered": _counts(*filt_acc)},
            "fall_outcomes": all_rows, "clips": out_clips,
        }, indent=1), encoding="utf-8")
        print(f"  JSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
