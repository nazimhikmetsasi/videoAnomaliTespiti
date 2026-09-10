"""Asama 8.3 (ikinci yari) oz kontrolu - agsiz, Docker'siz, veritabanisiz.

analitik/sistem-sagligi/kullanicilar/denetim-kaydi sayfa betiklerinin
build_frontend.py ciktisina eklendigini, requireAuth() cagrildigini ve
recall/f1 icin uydurma hesap yapilmadigini dogrular. Gercek veri/tarayici
dogrulamasi bu testin kapsami disinda (ASAMA8_PLAN.md SS3.8.3 onay kriteri).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_8_3b.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_frontend import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# sayfa betigi -> uretilmesi beklenen frontend/*.html
PAGES = {
    "analitik": "analitik.html",
    "sistem-sagligi": "sistem-sagligi.html",
    "kullanicilar": "kullanicilar.html",
    "denetim-kaydi": "denetim-kaydi.html",
}


def setup_module() -> None:
    # Betik idempotent -- her test kosusu once kendi girdisini uretir.
    build()


def _script_source(name: str) -> str:
    return (FRONTEND / "js" / f"{name}.js").read_text(encoding="utf-8")


def test_scripts_exist() -> None:
    for name in PAGES:
        assert (FRONTEND / "js" / f"{name}.js").is_file(), f"js/{name}.js yok"


def test_build_frontend_injects_page_script_tag() -> None:
    for name, out_name in PAGES.items():
        html = (FRONTEND / out_name).read_text(encoding="utf-8")
        assert f'src="js/{name}.js?v=' in html, out_name
        # app.js her zaman page-script'ten ONCE gelir (app.js'teki global'lere
        # sayfa betigi bagimli).
        assert html.index('src="js/app.js?v=') < html.index(f'src="js/{name}.js?v='), out_name


def test_every_script_calls_require_auth_first() -> None:
    for name in PAGES:
        src = _script_source(name)
        # Yorum satirlarini ve bos satirlari at, ilk gercek ifade requireAuth() olmali.
        code_lines = [
            line.strip() for line in src.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        assert code_lines, name
        assert code_lines[0] == "requireAuth();", (name, code_lines[0])


def test_analytics_never_computes_recall_or_f1() -> None:
    """QualityRowOut.recall/f1 backend'de her zaman None (ASAMA8_PLAN.md SS3.8.3
    / api/routers/analytics.py). Betik bu iki sutunu sabit "—" yazmali, ground
    truth olmadan bir hesap uretmemeli."""
    src = _script_source("analitik")
    assert 'tds[3].textContent = "—"' in src  # Duyarlilik (recall)
    assert 'tds[4].textContent = "—"' in src  # F1
    assert 'tds[1].textContent = "—"' in src  # Dogruluk (accuracy) -- hicbir ucta yok
    # row.recall / row.f1 hicbir aritmetik ifadede kullanilmamali.
    assert not re.search(r"row\.recall\s*[-+*/]", src)
    assert not re.search(r"row\.f1\s*[-+*/]", src)
    # QualityOut.note ekranda gorunur bir dipnot olarak baglanmali.
    assert "note.textContent = quality.note" in src


def test_forbidden_role_message_matches_backend() -> None:
    """api/auth.py require_role() 403'te sabit bir metin dondurur. Sabit
    Asama 8.4'te app.js'e tasindi (DURUM.md "Acik sorular" -- kopyalanmis
    yardimcilar); kullanicilar.js/denetim-kaydi.js artik FORBIDDEN_MSG'i
    KULLANIR, yeniden TANIMLAMAZ."""
    forbidden = "bu islem icin yetkiniz yok"
    auth_src = (ROOT / "api" / "auth.py").read_text(encoding="utf-8")
    assert forbidden in auth_src
    app_src = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    assert forbidden in app_src
    for name in ("kullanicilar", "denetim-kaydi"):
        assert "FORBIDDEN_MSG" in _script_source(name), name
        assert "const FORBIDDEN_MSG" not in _script_source(name), name
