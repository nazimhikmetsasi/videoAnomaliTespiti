"""Asama 13.2 Paket A: saglik boru hatti sirasi ve kanit listesi sayfalama."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects import postgresql  # noqa: E402

from api.routers.evidence import list_evidence  # noqa: E402
from api.routers.health import _LATEST_PIPELINE  # noqa: E402


def test_health_pipeline_sort_matches_index() -> None:
    assert _LATEST_PIPELINE[0] == {"$sort": {"camera_id": 1, "ts": -1}}


class _CaptureDB:
    def __init__(self) -> None:
        self.stmt = None

    def scalars(self, stmt):
        self.stmt = stmt
        return []


def _limit_offset(**kwargs) -> tuple[int, int]:
    db = _CaptureDB()
    list_evidence(db=db, _={}, **kwargs)
    # literal_binds renders LIMIT/OFFSET values; this stays DB-free
    sql = str(db.stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    tail = sql.split("LIMIT")[1].split("OFFSET")
    return int(tail[0]), int(tail[1])


def test_evidence_limit_offset_reach_statement() -> None:
    assert _limit_offset(limit=20, offset=40) == (20, 40)


def test_evidence_defaults_and_clamps() -> None:
    assert _limit_offset() == (50, 0)
    assert _limit_offset(limit=10_000)[0] == 500
    assert _limit_offset(limit=0)[0] == 1
