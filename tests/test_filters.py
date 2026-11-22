"""stream/filters.py: ic tipler hic gecmez, FALL/RUN davranisi degismez."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stream.filters import session_passes


def test_internal_types_never_pass():
    for tip in ("_TICK", "_EOS", "_x"):
        assert not session_passes(99, 99.0, tip, 0, {}, 0.0)


def test_fall_is_pulse():
    assert session_passes(2, 0.0, "FALL", 2)
    assert not session_passes(1, 0.0, "FALL", 2)


def test_run_needs_duration():
    assert session_passes(5, 1.0, "RUN", 2)
    assert not session_passes(5, 0.5, "RUN", 2)
