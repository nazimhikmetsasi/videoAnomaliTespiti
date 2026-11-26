"""POST /api/auth/login, GET /api/auth/me (ASAMA5_PLAN.md SS9.1)."""

from __future__ import annotations

import datetime
import math
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.auth import authenticate_user, bad_credentials, create_access_token, current_user
from api.db.postgres import get_db
from api.schemas import TokenOut, UserOut

router = APIRouter()


class LoginLimiter:
    """Kayan pencerede basarisiz giris sayaci (hesap ve IP basina). Dogru
    parola da kilitliyken denenmez; aksi halde sinir bir kahin olurdu."""

    def __init__(self, max_per_user: int = 10, max_per_ip: int = 30,
                 window_sec: float = 900.0, clock=time.monotonic) -> None:
        self.max_per_user, self.max_per_ip = max_per_user, max_per_ip
        self.window_sec, self._clock = window_sec, clock
        # ponytail: bellek ici, tek surec; birden cok iscide ortak depo (Redis/DB) gerekir
        self._users: dict[str, deque] = defaultdict(deque)
        self._ips: dict[str, deque] = defaultdict(deque)

    @staticmethod
    def _key(username: str) -> str:
        return username.strip().lower()

    def _prune(self, bucket: dict[str, deque], key: str) -> deque:
        q = bucket[key]
        cutoff = self._clock() - self.window_sec
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            bucket.pop(key, None)   # bos kovalar birikmesin
        return q

    def _wait(self, q: deque, limit: int) -> float:
        if len(q) < limit:
            return 0.0
        # en eski (len - limit)'inci girdi dusunce sayac limitin altina iner
        return q[len(q) - limit] + self.window_sec - self._clock()

    def retry_after(self, username: str, ip: str) -> float:
        wait = max(self._wait(self._prune(self._users, self._key(username)), self.max_per_user),
                   self._wait(self._prune(self._ips, ip), self.max_per_ip))
        return max(wait, 0.0)

    def failed(self, username: str, ip: str) -> None:
        now = self._clock()
        self._users[self._key(username)].append(now)
        self._ips[ip].append(now)

    def succeeded(self, username: str) -> None:
        self._users.pop(self._key(username), None)


login_limiter = LoginLimiter()


@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)) -> TokenOut:
    ip = request.client.host if request.client else "?"
    wait = login_limiter.retry_after(form.username, ip)
    if wait > 0:
        secs = math.ceil(wait)
        print(f"[auth] giris kilitli: kullanici={form.username.strip().lower()!r} ip={ip} {secs} sn")
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"cok fazla basarisiz deneme; {secs} sn sonra tekrar deneyin",
            headers={"Retry-After": str(secs)},
        )
    user = authenticate_user(db, form.username, form.password)
    if user is None:
        login_limiter.failed(form.username, ip)
        raise bad_credentials()
    login_limiter.succeeded(form.username)

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
