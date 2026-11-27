"""Asama 14A: saha degerlendirme aracinin saf mantigi (GPU yok)."""

import json
from collections import defaultdict
from types import SimpleNamespace

from eval.field_eval import confusion_table, load_events, match_outcomes, score_clip
from vision.rules.engine import Candidate


def outcome(fall_ts, kind="down", decided=25.0, track_id=1):
    return SimpleNamespace(fall_ts=fall_ts, outcome=kind, track_id=track_id,
                           metrics={"decided_after_sec": decided})


def fall(start, end, expected="down"):
    ev = {"type": "FALL", "start_sec": start, "end_sec": end}
    if expected:
        ev["outcome"] = expected
    return ev


def test_match_in_window():
    rows, un = match_outcomes([fall(10, 12)], [outcome(10.5, "down", 24.0)], 1.0)
    assert rows[0]["expected"] == "down" and rows[0]["found"] == "down"
    assert rows[0]["decided_after_sec"] == 24.0 and un == []


def test_match_tolerance_edge_and_outside():
    rows, un = match_outcomes([fall(10, 12)], [outcome(13.0)], 1.0)
    assert rows[0]["found"] == "down"
    rows, un = match_outcomes([fall(10, 12)], [outcome(13.5)], 1.0)
    assert rows[0]["found"] == "none" and rows[0]["decided_after_sec"] is None
    assert len(un) == 1


def test_match_nearest_of_several():
    outs = [outcome(9.2, "recovered", track_id=1), outcome(11.1, "down", track_id=2)]
    rows, un = match_outcomes([fall(10, 12)], outs, 1.0)
    assert rows[0]["found"] == "down"
    assert [o.track_id for o in un] == [1]


def test_fall_without_outcome_field_ignored():
    rows, un = match_outcomes([fall(10, 12, expected=None),
                               {"type": "RUN", "start_sec": 1, "end_sec": 2, "outcome": "down"}],
                              [outcome(10.5)], 1.0)
    assert rows == [] and len(un) == 1


def test_confusion_table_counts():
    rows = [{"expected": "down", "found": "down"}, {"expected": "down", "found": "none"},
            {"expected": "recovered", "found": "unknown"}]
    t = confusion_table(rows).splitlines()
    assert t[2] == "| down | 1 | 0 | 0 | 1 |"
    assert t[3] == "| recovered | 0 | 0 | 1 | 0 |"


def test_null_time_events_skipped(tmp_path):
    ann = tmp_path / "a.json"
    ann.write_text(json.dumps({"video": "x.mp4", "eval_end_sec": 50, "events": [
        {"type": "FALL", "start_sec": None, "end_sec": None, "outcome": "down"},
        {"type": "RUN", "start_sec": 3.0, "end_sec": 5.0}]}), encoding="utf-8")
    events, eval_end, skipped = load_events(ann)
    assert [e["type"] for e in events] == ["RUN"] and skipped == 1 and eval_end == 50
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_scoring_wiring_raw_and_filtered():
    def cand(t, ts, track=1):
        return Candidate(anomaly_type=t, track_ids=[track], score=1.0, idx=0, ts=ts,
                         metrics={}, thresholds_used={})
    # FALL: kalici 3 aday (oturum gecer); RUN: tek aday (Spark suzer)
    cands = [cand("FALL", 10.0), cand("FALL", 10.5), cand("FALL", 11.0),
             cand("RUN", 30.0, track=2)]
    events = [{"type": "FALL", "start_sec": 10, "end_sec": 12}]
    raw = (defaultdict(int), defaultdict(int), defaultdict(int))
    filt = (defaultdict(int), defaultdict(int), defaultdict(int))
    score_clip(cands, events, None, 1.0, raw, filt)
    assert raw[0]["FALL"] == 1 and raw[1]["RUN"] == 1
    assert filt[0]["FALL"] == 1 and filt[1].get("RUN", 0) == 0
