"""JWT kimlik dogrulama + rol denetimi. Sifre hash'i veritabaninda kalir --
Python tarafinda ikinci bir bcrypt uygulamasi yok (ASAMA5_PLAN.md SS1, SS3).
"""

from __future__ import annotations

import datetime
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import JWT_EXPIRE_MINUTES, JWT_SECRET
from api.db.postgres import get_db

ALGORITHM = "HS256"

# tokenUrl yalnizca Swagger'in "Authorize" formunu dogru uca yonlendirir;
# gercek dogrulama asagidaki current_user icindedir.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def bad_credentials() -> HTTPException:
    """Hatali kullanici adi ve hatali sifre AYNI mesaji dondurur (SS9.1) --
    hangi kullanicinin var oldugu sizdirilmaz."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="kullanici adi veya sifre hatali",
        headers={"WWW-Authenticate": "Bearer"},
    )


# UserOut'un tum alanlarini karsilar -- yalnizca crypt() karsilastirmasi icin
# gereken 5 sutunu almak (SS3'teki ornek sorgu) UserOut'u eksik doldururdu.
_USER_COLUMNS = "id, username, full_name, role, is_active, telegram_chat_id, last_login, created_at"


def authenticate_user(db: Session, username: str, password: str) -> dict[str, Any] | None:
    """crypt(sifre, mevcut_hash) mevcut hash'in tuzuyla yeniden hesaplar (SS3);
    parametreli sorgu -- sifre asla string birlestirmeyle SQL'e girmez."""
    row = db.execute(
        text(
            f"SELECT {_USER_COLUMNS} FROM users "
            "WHERE username = :username AND password_hash = crypt(:password, password_hash)"
        ),
        {"username": username, "password": password},
    ).mappings().first()
    return dict(row) if row else None


def create_access_token(user: dict[str, Any]) -> str:
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user["id"]), "username": user["username"], "role": user["role"], "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def current_user(token: str = Depends(_oauth2_scheme), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "gecersiz veya suresi gecmis jeton",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    row = db.execute(
        text(f"SELECT {_USER_COLUMNS} FROM users WHERE id = :id"),
        {"id": int(payload["sub"])},
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "gecersiz jeton")
    if not row["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "hesap devre disi")
    return dict(row)


def require_role(*roles: str):
    """Rol matrisi (ASAMA5_PLAN.md SS3): olay durumu -> operator+, kamera/
    bolge/esik yazma -> admin. Kullanim: Depends(require_role('admin'))."""

    def _check(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bu islem icin yetkiniz yok")
        return user

    return _check
