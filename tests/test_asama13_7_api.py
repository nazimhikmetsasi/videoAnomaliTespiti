"""Asama 13.7 paket A: giris deneme siniri, WS jeton iptali, CSV disa aktarma.
Veritabani gerektiren testler Postgres'e erisilemezse atlanir."""

from __future__ import annotations

import csv
import datetime
import io
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.auth import active_user_for_token, create_access_token, current_user
from api.routers import auth as auth_router
from api.routers.auth import LoginLimiter
from api.routers.events import csv_safe


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


# ------------------------------------------------------------ LoginLimiter
def test_limiter_locks_user_after_ten_failures() -> None:
    lim = LoginLimiter(clock=Clock())
    for _ in range(9):
        lim.failed("ali", "1.1.1.1")
    assert lim.retry_after("ali", "1.1.1.1") == 0
    lim.failed("ali", "1.1.1.1")
    assert lim.retry_after("ali", "1.1.1.1") > 0
    assert lim.retry_after("veli", "2.2.2.2") == 0   # baska hesap ve IP etkilenmez


def test_limiter_window_expires() -> None:
    clock = Clock()
    lim = LoginLimiter(clock=clock)
    for _ in range(10):
        lim.failed("ali", "1.1.1.1")
    assert lim.retry_after("ali", "1.1.1.1") == pytest.approx(900.0)
    clock.t += 899
    assert 0 < lim.retry_after("ali", "1.1.1.1") <= 1.0
    clock.t += 2
    assert lim.retry_after("ali", "1.1.1.1") == 0


def test_limiter_success_resets_user() -> None:
    lim = LoginLimiter(clock=Clock())
    for _ in range(10):
        lim.failed("ali", "1.1.1.1")
    lim.succeeded("ali")
    assert lim.retry_after("ali", "1.1.1.1") == 0


def test_limiter_ip_fills_across_accounts() -> None:
    lim = LoginLimiter(clock=Clock())
    for i in range(30):
        lim.failed(f"kullanici{i}", "9.9.9.9")
    assert lim.retry_after("yeni", "9.9.9.9") > 0
    assert lim.retry_after("yeni", "8.8.8.8") == 0


def test_limiter_username_case_and_space_insensitive() -> None:
    lim = LoginLimiter(clock=Clock())
    for name in ["Ali", "ALI", " ali ", "aLi", "ali"] * 2:
        lim.failed(name, "1.1.1.1")
    assert lim.retry_after("  ALI", "3.3.3.3") > 0


# --------------------------------------------------------------- login ucu
class _FakeDB:
    def execute(self, *a, **k):
        return None

    def commit(self) -> None:
        pass


def _login_client(monkeypatch, correct_password: str = "dogru"):
    from api.db.postgres import get_db

    calls = []
    user = {"id": 1, "username": "ali", "full_name": "Ali", "role": "viewer", "is_active": True,
            "telegram_chat_id": None, "last_login": None,
            "created_at": datetime.datetime.now(datetime.timezone.utc)}

    def fake_auth(db, username, password):
        calls.append(password)
        return user if password == correct_password else None

    monkeypatch.setattr(auth_router, "authenticate_user", fake_auth)
    monkeypatch.setattr(auth_router, "login_limiter", LoginLimiter())
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    return TestClient(app), calls


def _post(client, password: str, username: str = "ali"):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def test_login_429_on_eleventh_attempt(monkeypatch) -> None:
    client, _ = _login_client(monkeypatch)
    for _ in range(10):
        assert _post(client, "yanlis").status_code == 401
    r = _post(client, "yanlis")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert "tekrar deneyin" in r.json()["detail"]


def test_login_locked_ignores_correct_password(monkeypatch) -> None:
    client, calls = _login_client(monkeypatch)
    for _ in range(10):
        _post(client, "yanlis")
    n = len(calls)
    assert _post(client, "dogru").status_code == 429
    assert len(calls) == n, "kilitliyken parola denetlenmemeli"


def test_login_success_resets_counter(monkeypatch) -> None:
    client, _ = _login_client(monkeypatch)
    for _ in range(9):
        _post(client, "yanlis")
    assert _post(client, "dogru").status_code == 200
    for _ in range(9):
        assert _post(client, "yanlis").status_code == 401


# ---------------------------------------------------------------- csv_safe
def test_csv_safe() -> None:
    assert csv_safe("=1+1") == "'=1+1"
    assert csv_safe("-5") == "'-5"
    assert csv_safe("+1") == "'+1"
    assert csv_safe("@x") == "'@x"
    assert csv_safe("\tx") == "'\tx"
    assert csv_safe("\rx") == "'\rx"
    assert csv_safe("Giris kapisi") == "Giris kapisi"
    assert csv_safe(None) == ""


def test_export_route_declared_before_event_id() -> None:
    from api.routers.events import router

    paths = [r.path for r in router.routes]
    assert paths.index("/export.csv") < paths.index("/{event_id}")


# ------------------------------------------------------- veritabani testleri
def _live_session():
    from api.db.postgres import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    return db


@pytest.fixture()
def temp_user():
    """Gecici kullanici (rastgele parola, hic kullanilmaz); testten sonra silinir."""
    db = _live_session()
    name = f"t137_{uuid.uuid4().hex[:8]}"
    uid = db.execute(
        text("INSERT INTO users (username, password_hash, full_name, role) "
             "VALUES (:u, crypt(:p, gen_salt('bf')), 'Test', 'viewer') RETURNING id"),
        {"u": name, "p": uuid.uuid4().hex},
    ).scalar_one()
    db.commit()
    user = {"id": uid, "username": name, "role": "viewer"}
    try:
        yield db, user
    finally:
        db.rollback()
        db.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
        db.commit()
        db.close()


def _set_active(db, uid: int, active: bool) -> None:
    db.execute(text("UPDATE users SET is_active = :a WHERE id = :i"), {"a": active, "i": uid})
    db.commit()


def test_active_user_for_token(temp_user) -> None:
    import jwt

    from api.auth import ALGORITHM
    from api.config import JWT_SECRET

    db, user = temp_user
    token = create_access_token(user)
    got = active_user_for_token(db, token)
    assert got is not None and got["id"] == user["id"]

    assert active_user_for_token(db, None) is None
    assert active_user_for_token(db, token + "x") is None            # imza bozuk
    other = jwt.encode({"sub": str(user["id"]), "exp": datetime.datetime.now(datetime.timezone.utc)
                        + datetime.timedelta(minutes=5)}, "baska-sir", algorithm=ALGORITHM)
    assert active_user_for_token(db, other) is None                  # yanlis anahtar
    expired = jwt.encode({"sub": str(user["id"]), "exp": datetime.datetime.now(datetime.timezone.utc)
                          - datetime.timedelta(minutes=1)}, JWT_SECRET, algorithm=ALGORITHM)
    assert active_user_for_token(db, expired) is None
    ghost = create_access_token({"id": 2_000_000_000, "username": "yok", "role": "viewer"})
    assert active_user_for_token(db, ghost) is None                  # olmayan kullanici

    _set_active(db, user["id"], False)
    assert active_user_for_token(db, token) is None                  # pasif


def test_alerts_ws_rejects_inactive_user(temp_user) -> None:
    from starlette.websockets import WebSocketDisconnect

    from api.ws import alerts

    db, user = temp_user
    app = FastAPI()
    app.include_router(alerts.router)
    client = TestClient(app)
    token = create_access_token(user)

    with client.websocket_connect(f"/ws/alerts?token={token}"):
        pass   # etkinken baglanti kabul edilir

    _set_active(db, user["id"], False)
    with client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == 1008


@pytest.fixture()
def csv_data():
    """Gecici kamera + bolge + 3 olay (adlar enjeksiyon denemesi icerir)."""
    from api.db.models import Camera, Event, Zone

    db = _live_session()
    cam = Camera(name=f"=t137_{uuid.uuid4().hex[:6]}", source="x", source_type="file")
    db.add(cam)
    db.flush()
    zone = Zone(camera_id=cam.id, name="Giriş, \"kapı\"", zone_type="forbidden",
                polygon=[[0, 0], [1, 0], [1, 1]])
    db.add(zone)
    db.flush()
    base = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    specs = [("FALL", "high", "new", zone.id, [3, 4]), ("RUN", "low", "resolved", None, [7]),
             ("FALL", "high", "resolved", None, [1])]
    for i, (typ, sev, st, zid, tracks) in enumerate(specs):
        db.add(Event(camera_id=cam.id, zone_id=zid, anomaly_type=typ, track_ids=tracks,
                     confidence=0.9, severity=sev, decided_by="rule", status=st,
                     started_at=base + datetime.timedelta(minutes=i), duration_ms=2500))
    db.commit()
    try:
        yield db, cam
    finally:
        db.rollback()
        db.delete(cam)   # olaylar ve bolge ON DELETE CASCADE ile gider
        db.commit()
        db.close()


def _events_client():
    from api.db.mongo import get_mongo
    from api.db.postgres import get_db
    from api.routers.events import router

    class _Tele:
        def find_one(self, *a, **k):
            return None

    class _Mongo:
        telemetry = _Tele()

    app = FastAPI()
    app.include_router(router, prefix="/api/events")
    app.dependency_overrides[current_user] = lambda: {"id": 1, "role": "viewer"}
    app.dependency_overrides[get_mongo] = lambda: _Mongo()

    def _db():
        from api.db.postgres import SessionLocal
        with SessionLocal() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _rows(resp) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def test_export_csv_content(csv_data) -> None:
    _, cam = csv_data
    client = _events_client()
    r = client.get("/api/events/export.csv", params={"camera_id": cam.id})
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert r.headers["content-disposition"].startswith('attachment; filename="olaylar_')
    assert "x-truncated" not in r.headers
    rows = _rows(r)
    assert rows[0] == ["id", "kamera", "bolge", "tip", "onem", "karar_veren", "baslangic", "bitis",
                       "sure_sn", "guven", "durum", "dusme_sonucu", "iz"]
    assert len(rows) == 4
    newest, _, oldest = rows[1], rows[2], rows[3]
    assert newest[1] == "'" + cam.name                       # formul enjeksiyonu etkisiz
    assert oldest[2] == "Giriş, \"kapı\""          # virgul/tirnak csv ile korunur
    assert oldest[12] == "3;4"
    assert oldest[8] == "2.5"
    assert datetime.datetime.fromisoformat(oldest[6]).utcoffset() is not None


def test_export_csv_filters(csv_data) -> None:
    _, cam = csv_data
    client = _events_client()
    r = client.get("/api/events/export.csv",
                   params={"camera_id": cam.id, "anomaly_type": "FALL", "status": "resolved"})
    rows = _rows(r)
    assert len(rows) == 2 and rows[1][3] == "FALL" and rows[1][10] == "resolved"


def test_event_id_route_still_works(csv_data) -> None:
    client = _events_client()
    assert client.get("/api/events/2000000000").status_code == 404   # 422 degil
