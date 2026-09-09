"""storage/ kok dizini altinda guvenli yol cozumu (ASAMA7_PLAN.md SS5).

Bu kontrol daha once yalnizca api/routers/events.py::_safe_storage_path
icinde vardi ve HTTPException firlatiyordu. api/notify.py FastAPI disinda,
worker thread'inde calisir -- orada HTTP istisnasi anlamsizdir. Denetim bu
yuzden TEK YERE tasindi: events.py bunu cagirip kendi HTTPException'ini
kendisi atar, notify.py None donunce sadece fotografi atlar. Kopya yazilirsa
kok disina cikma denetimi iki yerde ayri ayri yasar ve biri geride kalir.
"""

from __future__ import annotations

from pathlib import Path

from api.config import STORAGE_DIR

_STORAGE_ROOT = Path(STORAGE_DIR).resolve()


def storage_path(relative: str) -> Path | None:
    """relative veritabanindan gelen DIS girdidir -- kok disina cikan yol
    (`../../etc/passwd` gibi) None doner, istisna firlatmaz."""
    candidate = (_STORAGE_ROOT / relative).resolve()
    if not candidate.is_relative_to(_STORAGE_ROOT):
        return None
    return candidate
