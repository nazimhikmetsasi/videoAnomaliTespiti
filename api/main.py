"""FastAPI giris noktasi: router kaydi, CORS, /health (ASAMA5_PLAN.md SS8/9.7)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError
from sqlalchemy import text

from api.config import FRONTEND_DIR
from api.db.migrate import run_migrations
from api.db.mongo import get_mongo
from api.db.postgres import engine
from api.matching import load_tolerance
from api.routers import (analytics, audit, auth, cameras, events, evidence, health,
                         notifications, settings, users, zones)
from api.ws import alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sema gocleri HER SEYDEN ONCE: init.sql yalnizca bos birimde kosar,
    # var olan kurulumda yeni sutunlar buradan gelir (api/db/migrate.py).
    if applied := run_migrations():
        print(f"  sema gocu uygulandi: {', '.join(applied)}")
    # Kanit-olay eslesme toleransi = spark_window_sec; acilista bir kez okunur
    # (api/matching.py, gerekcesi orada).
    load_tolerance()
    # Kirmizi alarm yayini (docs/ASAMA6_PLAN.md SS8.4): anomaly-events'i
    # ikinci kez okuyan Kafka tuketicisi, ayri thread'de. Kapanista durdurulur.
    alerts.broadcaster.start()
    yield
    alerts.broadcaster.stop()


app = FastAPI(title="Video Anomali Tespiti API", lifespan=lifespan)

# frontend/ ayri origin'den servis edilecek (Asama 8); pilot asamada kisitlama
# pratik deger katmiyor.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
app.include_router(zones.router, prefix="/api/zones", tags=["zones"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(evidence.router, prefix="/api/evidence", tags=["evidence"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(alerts.router, tags=["ws"])


@app.get("/health")
def health() -> dict:
    """Kimlik istemez -- Docker healthcheck ve panelin sistem sagligi ekrani
    bunu kullanir. Kontrol hafif: SELECT 1 / ping (SS9.7)."""
    pg_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pg_ok = False

    mongo_ok = True
    try:
        get_mongo().client.admin.command("ping")
    except PyMongoError:
        mongo_ok = False

    return {"status": "ok" if pg_ok and mongo_ok else "degraded", "postgres": pg_ok, "mongo": mongo_ok}


# Panel statik dosyalari (Asama 8, ASAMA8_PLAN.md SS1/SS3.8.1). "/api", "/ws"
# ve "/health" router'larindan SONRA -- StaticFiles "/" tum yollari yakalar,
# onlarin gorulmesi icin sirali kayit sart. Dizin yoksa mount atlanir: testler
# ve API-only kosu (docker-compose'suz, FRONTEND_DIR bos) bozulmaz.
if Path(FRONTEND_DIR).is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
