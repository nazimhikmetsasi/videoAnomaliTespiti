"""Asama 8.6 frontend oz kontrolu -- canli goru portu saglik ucundan cozulur,
olu/bayat kameraya korlemesine soket acilmaz (ASAMA8_PLAN.md 8.6 SS3).

Agsiz/Dockersiz kaynak-deseni kontrolu (8.5b ile ayni stil); gercek tarayici
dogrulamasi (N kutu -> tek istek, kopan kamera geri gelince kendiliginden
baglanma) bu testin kapsami disinda, ana oturum yapar.

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_frontend_8_6.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
LIVE_CALLERS = ("index", "kamera-detay", "bolgeler")


def _js(name: str) -> str:
    return (FRONTEND / "js" / f"{name}.js").read_text(encoding="utf-8")


def test_live_js_no_fixed_ws_port_constant() -> None:
    src = _js("live")
    assert "LIVE_WS_PORT" not in src


def test_live_ws_url_takes_port_argument() -> None:
    src = _js("live")
    assert re.search(r"function\s+liveWsUrl\(kind,\s*cameraId,\s*port\)", src)


def test_live_js_resolves_port_from_health_endpoint() -> None:
    src = _js("live")
    assert '"/api/health/cameras"' in src
    assert "healthWsPort" in src
    assert "ws_port" in src


def test_live_js_skips_socket_when_port_missing_or_stale() -> None:
    src = _js("live")
    assert "doc.ws_port == null" in src
    assert "STALE_SEC" in src and "age_sec" in src
    # openReconnectingSocket urlFn'in null donebilecegini bilmeli -- port
    # yoksa soket hic ACILMAZ.
    assert re.search(r"if\s*\(!url\)", src)


def test_live_js_health_cache_is_shared_not_per_camera() -> None:
    """N kutu ayni anda soruyor -- N istek DEGIL, TEK paylasilan yoklayici
    (zonesFor'daki onbellek deseniyle ayni ruh, tek anahtarli oldugu farkla)."""
    src = _js("live")
    assert "_healthPolling" in src
    assert "setInterval(_pollHealthOnce" in src


def test_callers_use_shared_live_url_fn() -> None:
    for name in LIVE_CALLERS:
        src = _js(name)
        assert "liveUrlFn(" in src, f"{name}.js liveUrlFn kullanmiyor"
        # Eski desen: liveWsUrl'i dogrudan arrow function icinde cagirmak --
        # port cozumu artik TEK yerde (live.js), burada tekrarlanmamali.
        assert not re.search(r"=>\s*liveWsUrl\(", src), f"{name}.js port cozumunu kopyaliyor"
