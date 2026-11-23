"""Asama 13.2 Paket F: panel XSS taramasi ve onbellek etiketi (agsiz, DB'siz).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_asama13_2_frontend.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_frontend  # noqa: E402

JS = Path(__file__).resolve().parents[1] / "frontend" / "js"


def _lines(name: str) -> list[str]:
    return (JS / f"{name}.js").read_text(encoding="utf-8").splitlines()


def test_olaylar_camera_name_and_location_escaped() -> None:
    line = next(ln for ln in _lines("olaylar") if "tds[3].innerHTML" in ln)
    assert "_escXml(_cameraName(" in line
    assert "_escXml(_cameraLocation(" in line


def test_server_text_sinks_escaped() -> None:
    # (dosya, innerHTML'e giren degisken) -- sunucudan gelen hata metni.
    sinks = [
        ("olaylar", "_escXml(msg)"),
        ("kameralar", "_escXml(msg)"),
        ("kamera-detay", "_escXml(msg)"),
        ("olay-detay", "_escXml(msg)"),
        ("denetim-kaydi", "${_escXml(text)}"),
        ("kullanicilar", "${_escXml(text)}"),
        ("index", "_escXml(e.message)"),
    ]
    for name, expected in sinks:
        src = "\n".join(_lines(name))
        assert expected in src, f"{name}.js: {expected} yok"


def test_versioned_hash_line_ending_independent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(build_frontend, "FRONTEND", tmp_path)
    (tmp_path / "js").mkdir()
    f = tmp_path / "js" / "a.js"
    f.write_bytes(b"x\ny\n")
    lf = build_frontend._versioned("js/a.js")
    f.write_bytes(b"x\r\ny\r\n")
    assert build_frontend._versioned("js/a.js") == lf
