"""FastAPI giris noktasi: router kaydi, CORS, /health (ASAMA5_PLAN.md SS8/9.7)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError
from sqlalchemy import text

from api.db.mongo import get_mongo
from api.db.postgres import engine
from api.routers import analytics, auth, cameras, events, settings, zones

app = FastAPI(title="Video Anomali Tespiti API")

# frontend/ ayri origin'den servis edilecek (Asama 8); pilot asamada kisitlama
# pratik deger katmiyor.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
app.include_router(zones.router, prefix="/api/zones", tags=["zones"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])


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
