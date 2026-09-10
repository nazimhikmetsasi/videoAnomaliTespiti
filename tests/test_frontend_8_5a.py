"""Asama 8.5 (ilk yari, 8.5a) oz kontrolu -- kamera/kullanici yazma formlari,
olaylarin toplu isaretlenmesi, olay detayin durum dugmeleri. Agsiz, Docker'siz,
DB'siz -- tests/test_frontend_8_3a.py stiliyle aynidir: build_frontend.py
ciktisindaki betik satirlarini ve kaynak desenlerini dogrular, saf JS
mantigini calistirmaz. Asil kanit tarayici kosusu (gorev tanimindaki
Dogrulama maddesi 5 -- bu testin gecmesi davranisin kanitlanmasi degildir).

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_8_5a.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_frontend import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
JS = FRONTEND / "js"

_TOUCHED_SCRIPTS = ["app.js", "kameralar.js", "kullanicilar.js", "olaylar.js", "olay-detay.js"]
_PAGE_SCRIPTS = {
    "kameralar.js": "kameralar.html",
    "olaylar.js": "olaylar.html",
    "olay-detay.js": "olay-detay.html",
    "kullanicilar.js": "kullanicilar.html",
}


def setup_module() -> None:
    build()


def _source(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


# ------------------------------------------------------------------- requireAuth
def test_every_page_script_still_calls_require_auth_first() -> None:
    for js_name, html_name in _PAGE_SCRIPTS.items():
        src = _source(js_name)
        lines = [l.strip() for l in src.splitlines() if l.strip() and not l.strip().startswith("//")]
        assert lines[0] == "requireAuth();", f"{js_name}: ilk calisan satir requireAuth() degil"
        html = (FRONTEND / html_name).read_text(encoding="utf-8")
        assert f'src="js/{js_name}?v=' in html


# ---------------------------------------------------------------------- app.js
def test_app_js_defines_open_form_dialog_with_native_dialog() -> None:
    src = _source("app.js")
    assert "async function openFormDialog(" in src
    assert 'document.createElement("dialog")' in src
    assert ".showModal()" in src
    assert "dialog.remove()" in src  # kapaninca DOM'dan kaldirilir


def test_app_js_form_dialog_does_not_swallow_write_errors() -> None:
    """openFormDialog kendisi api() cagirmaz -- yazma istegi ve hata gosterimi
    cagiran tarafta (girdi kaybi olmamasi icin, gorev tanimi)."""
    src = _source("app.js")
    start = src.index("async function openFormDialog(")
    end = src.index("\nasync function _wireProfileButton", start)
    body = src[start:end]
    assert "await api(" not in body
    assert "values.error" in body


# ----------------------------------------------------------------- kameralar.js
def test_kameralar_js_has_camera_crud_endpoints() -> None:
    src = _source("kameralar.js")
    assert 'api("/api/cameras", { method: "POST"' in src
    assert '"/api/cameras/" + existing.id, { method: "PUT"' in src
    assert '"/api/cameras/" + cam.id, { method: "DELETE"' in src


def test_kameralar_js_put_sends_full_body_not_partial() -> None:
    """CameraIn TAM govde bekler (kismi degil) -- duzenleme formu mevcut
    kameranin butun alanlarindan degerlerle doldurulur."""
    src = _source("kameralar.js")
    for field in ("name", "source", "source_type", "location", "width", "height", "target_fps", "is_active"):
        assert f'name: "{field}"' in src, f"kameralar.js: form alani eksik: {field}"


def test_kameralar_js_add_button_selector_is_narrow() -> None:
    """Kenar cubugu ayni sinif uclusunu tasidigi icin gorev tanimi dar/tek
    eslesen bir secici istiyor -- bg-secondary-container yalniz bu dugmede var."""
    src = _source("kameralar.js")
    assert 'querySelector("button.bg-secondary-container")' in src
    html = (FRONTEND / "kameralar.html").read_text(encoding="utf-8")
    assert html.count("bg-secondary-container") == 1


def test_kameralar_js_delete_confirms_and_reloads() -> None:
    src = _source("kameralar.js")
    assert "confirm(" in src
    assert "_load();" in src


# --------------------------------------------------------------- kullanicilar.js
def test_kullanicilar_js_has_user_crud_endpoints() -> None:
    src = _source("kullanicilar.js")
    assert 'api("/api/users", { method: "POST"' in src
    assert '"/api/users/" + existing.id, { method: "PUT"' in src
    assert '"/api/users/" + user.id, { method: "DELETE"' in src


def test_kullanicilar_js_delete_button_says_deactivate_not_delete() -> None:
    """DELETE gercek silme degil is_active=False (soft delete) -- dugme
    metni 'pasiflestir' olmali."""
    src = _source("kullanicilar.js")
    assert "pasifleştirmek" in src
    assert "_deactivateUser" in src


def test_kullanicilar_js_empty_password_is_not_sent_on_edit() -> None:
    src = _source("kullanicilar.js")
    assert "if (!body.password) delete body.password;" in src


def test_kullanicilar_js_role_options_come_from_shared_map() -> None:
    src = _source("kullanicilar.js")
    assert "Object.entries(ROLE_ADI)" in src


def test_kullanicilar_js_add_button_hidden_on_forbidden() -> None:
    src = _source("kullanicilar.js")
    assert "_addBtn.hidden = true" in src


# ------------------------------------------------------------------- olaylar.js
def test_olaylar_js_bulk_ack_patches_each_selected_event() -> None:
    src = _source("olaylar.js")
    assert '"/api/events/" + id, { method: "PATCH", body: { status: "acknowledged" } }' in src
    assert "Promise.all(" in src


def test_olaylar_js_checkbox_selection_keyed_by_event_id() -> None:
    """DOM sirasina degil olay id'sine gore eslenir (gorev tanimi notu)."""
    src = _source("olaylar.js")
    assert "checkbox.dataset.eventId = String(ev.id)" in src
    assert "_selected" in src


def test_olaylar_js_select_all_and_bulk_button_present() -> None:
    src = _source("olaylar.js")
    assert '_selectAllCb' in src
    assert '_bulkAckBtn' in src
    assert "_bulkAckBtn.disabled = true" in src  # bos secimde devre disi


def test_olaylar_js_row_checkboxes_still_stop_propagation() -> None:
    src = _source("olaylar.js")
    assert "checkbox.addEventListener(\"click\", (e) => e.stopPropagation());" in src


# ---------------------------------------------------------------- olay-detay.js
def test_olay_detay_js_status_buttons_patch_correct_targets() -> None:
    """EventStatusIn 'new' hedef kabul etmez -- ucuncu bir dugme yok, yalniz
    acknowledged/false_positive/resolved (gorev tanimi)."""
    src = _source("olay-detay.js")
    assert '"/api/events/" + ev.id, { method: "PATCH", body: { status: target } }' in src
    icon_map_line = next(l for l in src.splitlines() if "_STATUS_BUTTON_ICON = {" in l)
    for target in ("acknowledged", "false_positive", "resolved"):
        assert target in icon_map_line
    assert "new" not in icon_map_line


def test_olay_detay_js_disables_button_matching_current_status() -> None:
    src = _source("olay-detay.js")
    assert "btn.disabled = current === target" in src


def test_olay_detay_js_updates_status_badge_after_patch() -> None:
    src = _source("olay-detay.js")
    assert "_setStatusBadge(current)" in src
    assert "DURUM_ADI" in src


# ---------------------------------------------------- sablonlara elle diyalog eklenmedi
def test_generated_html_has_no_hand_authored_dialog_markup() -> None:
    """frontend/*.html UretILEN dosyadir -- diyalog DOM'u calisma zamaninda
    JS ile kuruluyor, sablona elle eklenmedi (gorev tanimindaki MUTLAK KURAL)."""
    for html_name in ("kameralar.html", "kullanicilar.html", "olaylar.html", "olay-detay.html"):
        html = (FRONTEND / html_name).read_text(encoding="utf-8")
        assert "openFormDialog" not in html
        assert "<dialog" not in html


def test_touched_scripts_are_syntactically_plausible() -> None:
    """Node yoksa gercek sozdizimi kontrolu ayri yapilir (Dogrulama maddesi 4) --
    burada yalnizca dosyalarin bos olmadigi ve dengeli parantez tasidigi
    kontrol edilir (agir bir JS parser'a bagimli olmadan ucuz bir tutarlilik testi)."""
    for name in _TOUCHED_SCRIPTS:
        src = _source(name)
        assert src.strip()
        assert src.count("{") == src.count("}"), f"{name}: dengesiz suslu parantez"
        assert src.count("(") == src.count(")"), f"{name}: dengesiz parantez"
