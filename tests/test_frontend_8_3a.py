"""Asama 8.3 (ilk yari) oz kontrolu -- kameralar/kamera-detay/olaylar/
olay-detay ekranlarina gercek veri baglama. Agsiz, Docker'siz, DB'siz.

Bu testler saf JS mantigini calistirmaz (Python'dan JS calistirilmiyor) --
build_frontend.py ciktisinda betik satirlarinin gercekten eklendigini,
her betigin requireAuth() ile actigini ve dogru uc/yardimci desenlerine
basvurdugunu dogrular. Asil kanit tarayici kosusu (gorev tanimindaki
Dogrulama maddesi 3).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_8_3a.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_frontend import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
JS = FRONTEND / "js"

# betik adi -> ürettigi sayfa (PAGES esitlemesiyle ayni, ASAMA8_PLAN.md SS3)
_PAGE_SCRIPTS = {
    "kameralar.js": "kameralar.html",
    "kamera-detay.js": "kamera-detay.html",
    "olaylar.js": "olaylar.html",
    "olay-detay.js": "olay-detay.html",
}


def setup_module() -> None:
    build()


def _source(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- build hattı
def test_page_scripts_exist() -> None:
    for name in _PAGE_SCRIPTS:
        assert (JS / name).is_file(), f"{name} yok"


def test_build_frontend_wires_each_page_script() -> None:
    """build_frontend.py'nin _page_script_tag'i js/<sayfa>.js varsa <script>
    satirini otomatik ekliyor (paylasimli dosyaya dokunmadan dogrulanan
    davranis) -- her sayfa hem app.js hem kendi betigini yuklemeli."""
    for js_name, html_name in _PAGE_SCRIPTS.items():
        html = (FRONTEND / html_name).read_text(encoding="utf-8")
        assert 'src="js/app.js"' in html, f"{html_name}: js/app.js eksik"
        assert f'src="js/{js_name}"' in html, f"{html_name}: js/{js_name} eksik"
        # app.js her zaman sayfa betiginden ONCE yuklenir (TIP_ADI/api/
        # requireAuth gibi globaller sayfa betigi calisirken hazir olmali).
        assert html.index('src="js/app.js"') < html.index(f'src="js/{js_name}"')


# ------------------------------------------------------------------- requireAuth
def test_every_page_script_calls_require_auth_first() -> None:
    """SS "Ortak davranis": her betik ilk satirda requireAuth() cagirir."""
    for js_name in _PAGE_SCRIPTS:
        src = _source(js_name)
        lines = [l.strip() for l in src.splitlines() if l.strip() and not l.strip().startswith("//")]
        assert lines[0] == "requireAuth();", f"{js_name}: ilk calisan satir requireAuth() degil"


# -------------------------------------------------------------------- kameralar.js
def test_kameralar_js_uses_cameras_endpoint_once() -> None:
    src = _source("kameralar.js")
    assert '"/api/cameras"' in src
    # Gorev tanimi: veri tek istekte gelir, filtreler sunucuya ikinci istek
    # atmaz -- kaynakta ikinci bir api("/api/cameras...") cagrisi olmamali.
    assert src.count('api("/api/cameras"') == 1


def test_kameralar_js_filters_client_side_and_links_to_detail() -> None:
    src = _source("kameralar.js")
    for token in ("_searchInput", "_statusSelect", "_locationSelect", "_applyFilters"):
        assert token in src
    assert "kamera-detay.html?id=" in src
    assert "rowTemplate(_tbody)" in src
    assert "Kayıt yok" in src  # bos durum


# ----------------------------------------------------------------- kamera-detay.js
def test_kamera_detay_js_reads_id_param_and_endpoints() -> None:
    src = _source("kamera-detay.js")
    assert "URLSearchParams(location.search)" in src
    assert '"/api/cameras/" + id' in src
    assert '"/api/events?camera_id=" + camId' in src
    assert "olay-detay.html?id=" in src


def test_kamera_detay_js_blanks_unwired_measurements() -> None:
    """8.4'un gercek FPS/dusen kare/cikarim suresi kutulari -- sahte sayi
    birakilmaz, "-" ile bosaltilir (gorev tanimi, Kamera Detay maddesi)."""
    src = _source("kamera-detay.js")
    assert 'fps.textContent = "—"' in src
    assert 'dropped.textContent = "—"' in src
    assert 'infer.textContent = "—"' in src


def test_kamera_detay_js_shows_error_when_id_missing_or_404() -> None:
    src = _source("kamera-detay.js")
    assert "_showFatalError" in src
    assert "if (!id)" in src


# --------------------------------------------------------------------- olaylar.js
def test_olaylar_js_uses_real_query_param_names() -> None:
    """api/routers/events.py'deki gercek parametre adlari (tahmin degil):
    camera_id, anomaly_type, severity, status, limit, offset."""
    src = _source("olaylar.js")
    for param in ("camera_id", "anomaly_type", "severity", "status", "limit", "offset"):
        assert f'"{param}"' in src, f"olaylar.js: {param} parametresi eksik"


def test_olaylar_js_populates_filters_from_shared_maps() -> None:
    src = _source("olaylar.js")
    assert "TIP_ADI" in src
    assert "SEVERITY_ADI" in src
    assert "DURUM_ADI" in src
    assert 'api("/api/cameras")' in src  # kamera acilir listesi icin ayri istek, izinli


def test_olaylar_js_binds_evidence_thumbnail_and_detail_link() -> None:
    src = _source("olaylar.js")
    assert '"/api/events/" + ev.id + "/frame"' in src
    assert "olay-detay.html?id=" in src
    assert "Kayıt yok" in src


# ----------------------------------------------------------------- olay-detay.js
def test_olay_detay_js_uses_event_id_and_evidence_endpoints() -> None:
    src = _source("olay-detay.js")
    assert '"/api/events/" + id' in src
    assert '"/api/events/" + ev.id + "/frame"' in src
    assert '"/api/events/" + ev.id + "/clip"' in src


def test_olay_detay_js_handles_missing_clip_and_missing_report() -> None:
    src = _source("olay-detay.js")
    assert "Kanıt klibi yok" in src
    assert "Rapor üretilmedi." in src
    assert "ev.llm_report_tr" in src


def test_olay_detay_js_shows_error_when_id_missing_or_404() -> None:
    src = _source("olay-detay.js")
    assert "_showFatalError" in src
    assert "if (!id)" in src


# ------------------------------------------------------ confidence tip tuzagi
def test_confidence_is_coerced_with_number_before_arithmetic() -> None:
    """ASAMA7'nin Decimal/string tuzagi: confidence uzerinde aritmetik
    yapmadan once Number() ile tip dogrulanmali (gorev tanimindaki uyari)."""
    for js_name in ("olaylar.js", "olay-detay.js"):
        src = _source(js_name)
        assert "Number(ev.confidence)" in src, f"{js_name}: confidence Number() ile cevrilmiyor"
        assert "Number.isFinite(conf)" in src, f"{js_name}: confidence gecersizlik kontrolu yok"
