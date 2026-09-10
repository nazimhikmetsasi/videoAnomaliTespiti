"""Asama 8.5b oz kontrolu - agsiz, Docker'siz, veritabanisiz.

bolgeler.js/ayarlar.js sayfa betiklerinin build_frontend.py ciktisina
eklendigini, requireAuth() cagrildigini, bolgeler.js'in direction tipini
sunmadigini ve letterbox donusumu yaptigini, ayarlar.js'in kismi PUT ve
spark_min_sec kopyalama kuralina uydugunu dogrular. Gercek veri/tarayici
dogrulamasi bu testin kapsami disinda (ASAMA8_PLAN.md SS3.8.5 onay kriteri).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_8_5b.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_frontend import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

PAGES = {
    "bolgeler": "bolgeler.html",
    "ayarlar": "ayarlar.html",
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
        assert f'<script src="js/{name}.js" defer></script>' in html, out_name
        assert html.index('src="js/app.js"') < html.index(f'src="js/{name}.js"'), out_name


def test_bolgeler_page_also_loads_live_js() -> None:
    # Bolge cizim arka plani canli kare gosterir -- live.js gerekir, app.js
    # ile kendi betigi arasinda yuklenmeli (build_frontend.py LIVE_PAGES).
    html = (FRONTEND / "bolgeler.html").read_text(encoding="utf-8")
    assert '<script src="js/live.js" defer></script>' in html
    assert html.index('src="js/app.js"') < html.index('src="js/live.js"') < html.index('src="js/bolgeler.js"')


def test_every_script_calls_require_auth_first() -> None:
    for name in PAGES:
        src = _script_source(name)
        code_lines = [
            line.strip() for line in src.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        assert code_lines, name
        assert code_lines[0] == "requireAuth();", (name, code_lines[0])


def test_bolgeler_writes_zone_endpoints() -> None:
    src = _script_source("bolgeler")
    assert '"/api/zones"' in src or "/api/zones" in src
    assert re.search(r"method:\s*[\"']POST[\"']", src)
    assert re.search(r"method:\s*[\"']PUT[\"']", src)
    assert re.search(r"method:\s*[\"']DELETE[\"']", src)
    assert "/api/zones/" in src  # PUT/DELETE tek bolgeye {id} ile gider


def test_bolgeler_does_not_offer_direction_zone_type() -> None:
    """vision/rules/zone.py ve loiter.py yalnizca forbidden/restricted_hours
    tanir -- direction tipinde bolge hicbir kurali beslemez (ASAMA8_PLAN.md
    SS4), sablondaki 4 sahte secenek yerine JS'te yalnizca bu ikisi sunulur."""
    src = _script_source("bolgeler")
    # Yorumlarda gerekce olarak "direction" gecebilir (yukaridaki docstring
    # gibi) -- kontrol yalnizca KOD satirlarinda, ozellikle secenek
    # listesinde bu deger sunulmadigini dogrulamali.
    code_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    code = "\n".join(code_lines)
    assert '"forbidden"' in code
    assert '"restricted_hours"' in code
    assert '"direction"' not in code
    assert "ters_yon" not in code  # sablonun sahte secenegi kod olarak tasinmamali


def test_bolgeler_applies_letterbox_transform_and_clips_out_of_range() -> None:
    src = _script_source("bolgeler")
    # live.js drawOverlay ile AYNI olcek formulu: scale = min(cssW/W, cssH/H)
    assert "Math.min" in src
    assert re.search(r"offX\s*=", src)
    assert re.search(r"offY\s*=", src)
    # letterbox seridine (0-1 disi) tiklama yok sayilir, kirpma yapilmaz.
    assert re.search(r"nx\s*<\s*0", src)
    assert re.search(r"nx\s*>\s*1", src)
    assert re.search(r"ny\s*<\s*0", src)
    assert re.search(r"ny\s*>\s*1", src)


def test_ayarlar_puts_settings_with_only_changed_fields() -> None:
    src = _script_source("ayarlar")
    assert "/api/settings" in src
    assert re.search(r"method:\s*[\"']PUT[\"']", src)
    # Kaynakta yuklenen deger ile mevcut form degeri karsilastirilmali --
    # sabit/tam govde PUT degil, yalnizca degisen alanlar gonderilmeli.
    assert re.search(r"current\[k\]\s*!==\s*loaded\[k\]", src)
    assert "restart_required" in src  # sunucudan okunur
    # Sabit liste yazilmamali -- pose_conf/track_conf/window_frames RESTART_REQUIRED
    # icerigi istemcide TEKRAR TANIMLANMAMALI.
    assert not re.search(r"restart_?required\s*=\s*\[", src, re.IGNORECASE)


def test_ayarlar_copies_spark_min_sec_dict_before_editing() -> None:
    """spark_min_sec kismi PUT alan bazinda calisir, sozluk ICI anahtar
    bazinda degil -- sunucudan gelen sozlugun TAMAMI kopyalanip yalnizca
    ilgili anahtar degistirilmeli, yoksa diger anomali tiplerinin suresi
    (orn. LOITERING) sessizce silinir."""
    src = _script_source("ayarlar")
    assert "Object.assign({}, loaded.spark_min_sec)" in src
    # Sadece {FALL: ...} veya {FIGHT: ...} gonderen kisayol olmamali.
    assert not re.search(r"spark_min_sec:\s*\{\s*FALL", src)
    assert not re.search(r"spark_min_sec:\s*\{\s*FIGHT", src)


# --------------------------------------------------- window_frames regresyonu
def test_ayarlar_js_window_frames_listede_yoksa_secenek_ekler() -> None:
    """Sablonun <select>'i yalniz 15/30/60/90 sunuyor, veritabani varsayilani
    50. Listede olmayan degeri atamak select.value'yu bos birakir, Number("")
    = 0 olur ve her kaydetmede window_frames=0 gonderilirdi -- tarayici
    kosusunda global satir gercekten 50'den 0'a dustu (docs/DURUM.md 8.5)."""
    src = _script_source("ayarlar")
    assert "_setWindowFrames" in src
    assert "windowSelect.appendChild(opt)" in src
    # Ham atama kalmamali: deger her zaman _setWindowFrames'ten gecmeli.
    assert "windowSelect.value = String(s.window_frames)" not in src
