"""GET /api/health/cameras -- kamera basina en son saglik durumu
(ASAMA8_PLAN.md SS3.8.2). Kaynak Mongo `camera_health`, vision/health_client.py
Asama 6'dan beri yaziyor (camera_id METIN -- ad ya da id, ts BSON Date,
fps_actual, dropped, infer_ms, gpu_mem, queue_depth).

`/health` (api/main.py) kimlik istemez, Docker healthcheck ve panelin genel
durum kartlari icindir. Bu uc YENI ve kimlik ISTER: kamera basina telemetri
disariya acik olmamali.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from pymongo.database import Database
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import current_user
from api.db.models import Camera
from api.db.mongo import get_mongo
from api.db.postgres import get_db
from api.routers.cameras import resolve_camera_id
from api.schemas import CameraHealthOut

router = APIRouter()


def _latest_health_docs(mongo: Database) -> dict[str, dict]:
    """camera_health'teki her HAM camera_id degeri (ad ya da id metni) icin
    en son belge -- kamera basina ayri sorgu yerine tek aggregate (N+1 yok)."""
    pipeline = [{"$sort": {"ts": -1}}, {"$group": {"_id": "$camera_id", "doc": {"$first": "$$ROOT"}}}]
    return {row["_id"]: row["doc"] for row in mongo.camera_health.aggregate(pipeline)}


def _to_health_out(cam: Camera, doc: dict | None, now: datetime.datetime) -> CameraHealthOut:
    if doc is None:
        # Mongo kaydi olmayan kamera da listede kalir, olcum alanlari null --
        # panelin "Baglanti Yok" durumu.
        return CameraHealthOut(camera_id=cam.id, name=cam.name)
    ts = doc["ts"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return CameraHealthOut(
        camera_id=cam.id, name=cam.name,
        fps_actual=doc.get("fps_actual"), dropped=doc.get("dropped"),
        infer_ms=doc.get("infer_ms"), gpu_mem=doc.get("gpu_mem"),
        queue_depth=doc.get("queue_depth"),
        # Belgenin yasi -- panel bayat veriyi canli sanmasin.
        age_sec=(now - ts).total_seconds(),
    )


@router.get("/cameras", response_model=list[CameraHealthOut])
def cameras_health(
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo),
    _: dict = Depends(current_user),
) -> list[CameraHealthOut]:
    now = datetime.datetime.now(datetime.timezone.utc)
    cams = list(db.scalars(select(Camera).order_by(Camera.id)))
    by_raw_id = _latest_health_docs(mongo)

    # Ham camera_id (ad veya id metni) -> gercek kamera id'sine coz. Ayni
    # cozum vision/'in kullandigi ile (api/routers/cameras.py) -- ikinci
    # bir ad-veya-id sorgusu yazilmaz.
    by_camera_id: dict[int, dict] = {}
    for raw_id, doc in by_raw_id.items():
        resolved = resolve_camera_id(db, raw_id)
        if resolved is not None:
            by_camera_id[resolved] = doc

    return [_to_health_out(cam, by_camera_id.get(cam.id), now) for cam in cams]
