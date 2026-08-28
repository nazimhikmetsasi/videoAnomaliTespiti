"""POST /api/auth/login, GET /api/auth/me (ASAMA5_PLAN.md SS9.1)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.auth import authenticate_user, bad_credentials, create_access_token, current_user
from api.db.postgres import get_db
from api.schemas import TokenOut, UserOut

router = APIRouter()


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    user = authenticate_user(db, form.username, form.password)
    if user is None:
        raise bad_credentials()

    db.execute(
        text("UPDATE users SET last_login = :now WHERE id = :id"),
        {"now": datetime.datetime.now(datetime.timezone.utc), "id": user["id"]},
    )
    db.commit()

    token = create_access_token(user)
    return TokenOut(access_token=token, user=UserOut(**user))


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)) -> UserOut:
    return UserOut(**user)
