"""Asama 8.1 oz kontrolu - agsiz, Docker'siz, veritabanisiz.

scripts/build_frontend.py'nin urettigi frontend/*.html'in sablon/ tasarimini
bozmadigini (SS3'teki tek izinli degisiklik: href + <script> satiri) ve
api/main.py'nin FRONTEND_DIR yokken de calistigini dogrular.

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_asama8.py -q
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_frontend import (  # noqa: E402
    _LOGIN_REPLACEMENTS, _SCRIPT_TAG, NAV_TARGETS, PAGES, build,
)

ROOT = Path(__file__).resolve().parents[1]
SABLON = ROOT / "sablon"
FRONTEND = ROOT / "frontend"

_CLASS_ATTR = re.compile(r'class="[^"]*"')
_A_HASH_LABELED = re.compile(r'<a\b[^>]*?href="#"[^>]*?>.*?</a>', re.DOTALL)


def setup_module() -> None:
    # Betik idempotent -- her test kosusu once kendi girdisini uretir, sablon/
    # elle degistirilmis olsa bile testler guncel frontend/'e bakar.
    build()


# login.html (sablon/girisekrani) kenar cubugu tasimaz, sahte davranisi gercek
# uca baglama disinda tasarima dokunulmayan 11 sayfayla ayni denetimden gecmez
# -- kendi ozel denetimi asagida test_login_diff_is_only_declared_changes.
_SIDEBAR_PAGES = {k: v for k, v in PAGES.items() if k != "girisekrani"}


# ------------------------------------------------------- gezinme baglantilari
def test_sidebar_links_point_to_real_files() -> None:
    for out_name in _SIDEBAR_PAGES.values():
        html = (FRONTEND / out_name).read_text(encoding="utf-8")
        for label, target in NAV_TARGETS.items():
            assert label in html, f"{out_name}: '{label}' etiketi bulunamadi"
            assert f'href="{target}"' in html, f"{out_name}: {label} -> {target} baglantisi yok"
            assert (FRONTEND / target).is_file(), f"{out_name}: hedef {target} frontend/ icinde yok"


def test_no_dangling_hash_href_for_sidebar_labels() -> None:
    """Kenar cubugu disindaki href="#" (ornegin geri oku) dokunulmadan kalabilir
    -- yalnizca ETIKETI bilinen 9 baglantidan biri olan href="#" kalmamali."""
    for out_name in _SIDEBAR_PAGES.values():
        html = (FRONTEND / out_name).read_text(encoding="utf-8")
        for m in _A_HASH_LABELED.finditer(html):
            text = re.sub(r"<[^>]+>", " ", m.group(0))
            for label in NAV_TARGETS:
                assert label not in text, f"{out_name}: '{label}' hala href=# ile birakilmis"


# ------------------------------------------------------------------- js/app.js
def test_every_page_includes_app_js() -> None:
    for out_name in PAGES.values():
        html = (FRONTEND / out_name).read_text(encoding="utf-8")
        assert 'src="js/app.js"' in html, f"{out_name}: js/app.js eklenmemis"


# --------------------------------------------------- tasarim korunuyor kaniti
def test_only_href_and_script_lines_differ_from_template() -> None:
    for src_dir, out_name in _SIDEBAR_PAGES.items():
        with open(SABLON / src_dir / "code.html", encoding="utf-8", newline="") as f:
            template_lines = f.read().splitlines()
        with open(FRONTEND / out_name, encoding="utf-8", newline="") as f:
            built_lines = f.read().splitlines()

        # Eklenen tek satir: js/app.js script'i (build_frontend.py SS3).
        assert len(built_lines) == len(template_lines) + 1, out_name
        script_lines = [i for i, line in enumerate(built_lines) if 'src="js/app.js"' in line]
        assert len(script_lines) == 1, out_name
        del built_lines[script_lines[0]]

        assert len(built_lines) == len(template_lines), out_name
        for t_line, b_line in zip(template_lines, built_lines):
            if t_line == b_line:
                continue
            # href="#" -> href="<hedef>.html" disinda fark olmamali.
            assert 'href="#"' in t_line and re.sub(r'href="#"', 'href="X"', t_line) == \
                re.sub(r'href="[^"]*\.html"', 'href="X"', b_line), (
                out_name, t_line, b_line,
            )

        # Sinif niteliklerinin kumesi (sirali) birebir ayni -- tasarima
        # dokunulmadiginin kaniti.
        assert _CLASS_ATTR.findall("\n".join(template_lines)) == \
            _CLASS_ATTR.findall("\n".join(built_lines)), out_name


def test_login_diff_is_only_declared_changes() -> None:
    """login.html'in sablondan TEK farki js/app.js satiri + koordinasyonla
    kararlastirilan davranis degisiklikleri (demo kimlik bilgileri, sahte
    simulateLogin, "2FA"/oturum-suresi ogeleri) olmali. _LOGIN_REPLACEMENTS'i
    (yeni -> eski) geri uygulayip sablonu birebir yeniden kurarak kanitlar --
    baska hicbir satirin degismedigini gosterir."""
    with open(SABLON / "girisekrani" / "code.html", encoding="utf-8", newline="") as f:
        template = f.read()
    with open(FRONTEND / "login.html", encoding="utf-8", newline="") as f:
        built = f.read()

    assert built.count(_SCRIPT_TAG) == 1
    reconstructed = built.replace(_SCRIPT_TAG, "", 1)
    # Ileri sirada geri al: iki quickFill() cagrisi ayni metne sadelesiyor
    # (onclick="quickFill()"), sirali replace(..., 1) soldan sagadir --
    # belgedeki soldan-saga sirayla ayni sirada geri almak konumu korur.
    for old, new in _LOGIN_REPLACEMENTS:
        assert new in reconstructed, f"beklenen degisiklik yok: {new[:60]!r}"
        reconstructed = reconstructed.replace(new, old, 1)

    assert reconstructed == template


# ------------------------------------------------------------- FRONTEND_DIR
def test_api_main_imports_without_frontend_dir() -> None:
    # Alt surecte calistirilir: bu test dosyasi veya baska bir test daha once
    # api.main'i import etmis olabilir, modul onbellegi gercek durumu gizler.
    env_clear = "import os; os.environ.pop('FRONTEND_DIR', None); import api.main"
    result = subprocess.run(
        [sys.executable, "-c", env_clear], cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
