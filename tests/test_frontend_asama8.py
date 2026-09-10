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
    _LOGIN_REPLACEMENTS, _REMOTE_IMG, _script_tag, LIVE_PAGES, NAV_TARGETS,
    PAGES, PLACEHOLDER_IMG, build,
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
        assert 'src="js/app.js?v=' in html, f"{out_name}: js/app.js eklenmemis"


# --------------------------------------------------- tasarim korunuyor kaniti
def test_only_href_and_script_lines_differ_from_template() -> None:
    for src_dir, out_name in _SIDEBAR_PAGES.items():
        with open(SABLON / src_dir / "code.html", encoding="utf-8", newline="") as f:
            template_lines = f.read().splitlines()
        with open(FRONTEND / out_name, encoding="utf-8", newline="") as f:
            built_lines = f.read().splitlines()

        # Eklenen satirlar: js/app.js, -- LIVE_PAGES'te ise -- js/live.js, ve
        # -- varsa -- sayfaya ozel betik (build_frontend.py _page_script_tag,
        # Asama 8.3'ten beri). Uc de betik satiridir; tasarim kanitindan once
        # ayiklanir.
        script_lines = [i for i, line in enumerate(built_lines) if 'src="js/' in line]
        assert len([i for i in script_lines if 'src="js/app.js?v=' in built_lines[i]]) == 1, out_name
        max_scripts = 3 if out_name in LIVE_PAGES else 2
        assert len(script_lines) <= max_scripts, (out_name, script_lines)
        assert len(built_lines) == len(template_lines) + len(script_lines), out_name
        for i in reversed(script_lines):
            del built_lines[i]

        assert len(built_lines) == len(template_lines), out_name
        for t_line, b_line in zip(template_lines, built_lines):
            if t_line == b_line:
                continue
            # Izinli iki fark: href="#" -> href="<hedef>.html" ve uzak
            # gorsel baglantisi -> yerel yer tutucu (build_frontend SS1).
            t_norm = _REMOTE_IMG.sub(PLACEHOLDER_IMG, re.sub(r'href="#"', 'href="X"', t_line))
            b_norm = re.sub(r'href="[^"]*\.html"', 'href="X"', b_line)
            assert t_norm == b_norm, (out_name, t_line, b_line)

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

    # Betik etiketi 8.6'dan beri icerik ozetiyle surumleniyor
    # (js/app.js?v=<hash>) -- onbellek sorunu icin, bkz. build_frontend._versioned
    app_tag = _script_tag("js/app.js")
    assert built.count(app_tag) == 1
    reconstructed = built.replace(app_tag, "", 1)
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
