"""Asama 13.3a oz kontrolu: kare hizi tarama araci (GPU ve veri gerektirmez).

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_3_olcum.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.pilot_eval import load_annotation  # noqa: E402
from eval.tcn_eval import compare_table, expand_configs, session_filter, totals  # noqa: E402
from models.tcn import FrameDropper  # noqa: E402
from vision.rules.engine import Candidate  # noqa: E402


def kept_indices(source_fps: float, target_fps: float, n: int, **kw) -> list[int]:
    d = FrameDropper(target_fps, **kw)
    return [i for i in range(n) if d(i / source_fps)]


def cand(kind: str, ts: float, tracks=(1,)) -> Candidate:
    return Candidate(kind, list(tracks), 1.0, int(ts * 25), ts, {}, {})


def test_regular_25_to_5():
    assert kept_indices(25, 5, 30) == [0, 5, 10, 15, 20, 25]


def test_regular_30_to_10_every_third():
    assert kept_indices(30, 10, 30) == list(range(0, 30, 3))


def test_regular_29_97_to_10_keeps_average():
    assert abs(len(kept_indices(29.97, 10, 300)) - 100) <= 1


def test_target_above_source_keeps_all():
    assert kept_indices(15, 30, 50) == list(range(50))
    assert kept_indices(15, 0, 50) == list(range(50))


def test_jitter_seeded_and_average_rate():
    a = kept_indices(30, 10, 10000, mode="jitter", seed=7)
    assert a == kept_indices(30, 10, 10000, mode="jitter", seed=7)
    assert a != kept_indices(30, 10, 10000, mode="jitter", seed=8)
    assert abs(len(a) / (10000 / 30) - 10) <= 0.5


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        FrameDropper(10, mode="x")


def test_gap_does_not_burst():
    d = FrameDropper(10)
    assert d(0.0)
    assert d(5.0)                      # bosluktan sonra ilk kare tutulur
    assert not d(5.05) and d(5.1)      # sonra duzenli hiza doner


def test_session_filter_rules():
    assert session_filter([cand("FALL", 1.0)]) == []                      # hits = 1
    assert len(session_filter([cand("FALL", 1.0), cand("FALL", 1.04)])) == 2
    short = [cand("RUN", 1.0 + 0.04 * i) for i in range(5)]               # 0.16 sn < 1 sn
    assert session_filter(short) == []
    long_ = [cand("RUN", 1.0 + 0.2 * i) for i in range(6)]                # 1.0 sn
    assert len(session_filter(long_)) == 6


def test_session_split_by_gap_and_track():
    c = [cand("FALL", 1.0), cand("FALL", 1.1), cand("FALL", 9.0)]         # ikinci oturum tek aday
    assert len(session_filter(c)) == 2
    other = [cand("FALL", 1.0, (1,)), cand("FALL", 1.1, (2,))]           # farkli iz: her biri 1 vurus
    assert session_filter(other) == []


def test_load_annotation_drops_after_eval_end(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"eval_end_sec": 28, "events": [
        {"type": "RUN", "start_sec": 3, "end_sec": 5},
        {"type": "ZONE_VIOLATION", "start_sec": 30, "end_sec": 33}]}), encoding="utf-8")
    events, end = load_annotation(p)
    assert end == 28 and [e["type"] for e in events] == ["RUN"]
    p.write_text(json.dumps({"events": [{"type": "RUN", "start_sec": 99, "end_sec": 100}]}),
                 encoding="utf-8")
    assert load_annotation(p)[1] is None and len(load_annotation(p)[0]) == 1


def test_expand_configs():
    assert expand_configs([0], ["regular", "jitter"], [0, 1, 2]) == [(0.0, "native", 0)]
    cfgs = expand_configs([10], ["jitter"], [0, 1, 2])
    assert cfgs == [(10.0, "jitter", 0), (10.0, "jitter", 1), (10.0, "jitter", 2)]
    assert expand_configs([10, 5], ["regular"], [4]) == [(10.0, "regular", 0), (5.0, "regular", 0)]


def test_totals_micro():
    p, r, f1 = totals({"A": {"tp": 1, "fp": 1, "fn": 0}, "B": {"tp": 1, "fp": 0, "fn": 2}})
    assert (p, round(r, 3)) == (2 / 3, 0.5) and f1 == pytest.approx(2 * p * r / (p + r))


def _row(fps, drop, seed, tp, fp, fn):
    c = {"FALL": {"tp": tp, "fp": fp, "fn": fn}}
    return {"mode": "rule", "set": "pilot", "fps": fps, "drop": drop, "seed": seed,
            "eff_fps": fps, "raw": c, "filtered": c, "clips": {}}


def test_compare_aggregates_seeds(tmp_path):
    a = {"meta": {"holdout": ["x"]}, "rows": [_row(10.0, "jitter", 0, 1, 1, 0),
                                              _row(10.0, "jitter", 1, 1, 0, 0),
                                              _row(5.0, "regular", 0, 1, 0, 0)]}
    b = {"meta": {"holdout": ["y"]}, "rows": [_row(10.0, "jitter", 0, 1, 0, 0)]}
    for name, d in (("a.json", a), ("b.json", b)):       # dosyadan okunur bicim
        (tmp_path / name).write_text(json.dumps(d), encoding="utf-8")
    out = compare_table(*(json.loads((tmp_path / n).read_text()) for n in ("a.json", "b.json")))
    assert "UYARI" in out
    assert "0.83 [0.67, 1.00] -> 1.00" in out            # jitter: ortalama [min, maks]
    assert "| 5 | regular | 1.00 -> - |" in out          # yalniz A'da
