"""Asama 13.7 Paket G: olaylar.js CSV dugmesi (statik kaynak denetimi)."""

from __future__ import annotations

from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "frontend" / "js" / "olaylar.js").read_text(encoding="utf-8")


def test_csv_button_and_request() -> None:
    assert "CSV indir" in SRC
    assert "/api/events/export.csv" in SRC
    assert '"Authorization"' in SRC or "Authorization:" in SRC


def test_csv_download_cleanup_and_error() -> None:
    assert "download" in SRC and "revokeObjectURL" in SRC
    assert "olaylar.csv" in SRC and "Content-Disposition" in SRC
    assert "CSV indirilemedi" in SRC


def test_csv_excludes_paging() -> None:
    # export url is built from the shared filter params, never limit/offset
    start = SRC.index("function _filterParams")
    body = SRC[start:SRC.index("function _buildQuery")]
    assert "limit" not in body and "offset" not in body
