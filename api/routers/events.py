"""GET/PATCH /api/events, GET /api/events/{id} (ASAMA5_PLAN.md SS9.5)."""

from __future__ import annotations

import csv
import datetime
import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from pymongo.database import Database
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.audit import write_audit
from api.auth import current_user, require_role
from api.db.mongo import get_mongo
from api.db.models import Camera, Event, Zone
from api.db.postgres import get_db
from api.schemas import EventDetailOut, EventListOut, EventOut, EventStatusIn
from api.storage_paths import storage_path

router = APIRouter()

EXPORT_MAX_ROWS = 50_000
CSV_HEADER = ["id", "kamera", "bolge", "tip", "onem", "karar_veren", "baslangic", "bitis",
              "sure_sn", "guven", "durum", "dusme_sonucu", "iz"]


def csv_safe(value: object) -> str:
    """CSV formul enjeksiyonu: hucre = + - @ tab CR ile basliyorsa tablo
    programi formul sayar; basina ' konur. None -> bos."""
    if value is None:
        return ""
    text_ = str(value)
    return "'" + text_ if text_[:1] in ("=", "+", "-", "@", "\t", "\r") else text_


def _event_filters(camera_id, anomaly_type, status_, severity, decided_by, from_, to) -> list:
    # idx_events_camera_time / idx_events_time bu filtre kumesiyle uyumlu.
    # list_events ve export.csv ortak kullanir: iki ucta kopya olmasin.
    filters = []
    if camera_id is not None:
        filters.append(Event.camera_id == camera_id)
    if anomaly_type is not None:
        filters.append(Event.anomaly_type == anomaly_type)
    if status_ is not None:
        filters.append(Event.status == status_)
    if severity is not None:
        filters.append(Event.severity == severity)
    if decided_by is not None:
        filters.append(Event.decided_by == decided_by)
    if from_ is not None:
        filters.append(Event.started_at >= from_)
    if to is not None:
        filters.append(Event.started_at <= to)
    return filters


def _local_iso(dt: datetime.datetime | None) -> str:
    # llm._format_zaman ile ayni yaklasim: astimezone() yerel saat
    return dt.astimezone().isoformat(timespec="seconds") if dt else ""


def _safe_storage_path(relative: str) -> Path:
    """storage_path() SS8.3 kontrolunu tasir (ASAMA7_PLAN.md SS5) -- burada
    yalnizca None -> HTTPException(400) donusumu kalir."""
    path = storage_path(relative)
    if path is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "gecersiz kanit yolu")
    return path


@router.get("", response_model=EventListOut)
def list_events(
    camera_id: int | None = None,
    anomaly_type: str | None = None,
    status_: str | None = Query(None, alias="status"),
    severity: str | None = None,
    decided_by: str | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: dict = Depends(current_user),
) -> EventListOut:
    limit = min(max(limit, 1), 500)     # tavan 500 (SS9.5)

    filters = _event_filters(camera_id, anomaly_type, status_, severity, decided_by, from_, to)
    total = db.scalar(select(func.count()).select_from(Event).where(*filters)) or 0
    stmt = select(Event).where(*filters).order_by(Event.started_at.desc()).limit(limit).offset(offset)
    return EventListOut(total=total, items=list(db.scalars(stmt)))


@router.get("/export.csv")
def export_events_csv(
    camera_id: int | None = None,
    anomaly_type: str | None = None,
    status_: str | None = Query(None, alias="status"),
    severity: str | None = None,
    decided_by: str | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    _: dict = Depends(current_user),
) -> Response:
    # /{event_id}'den ONCE tanimli: yoksa "export.csv" kimlik sanilip 422 doner.
    filters = _event_filters(camera_id, anomaly_type, status_, severity, decided_by, from_, to)
    stmt = select(Event).where(*filters).order_by(Event.started_at.desc()).limit(EXPORT_MAX_ROWS + 1)
    events = list(db.scalars(stmt))
    truncated = len(events) > EXPORT_MAX_ROWS
    events = events[:EXPORT_MAX_ROWS]

    # id -> ad haritasi: satir basina sorgu (N+1) yerine iki kucuk sorgu
    cam_ids = {e.camera_id for e in events}
    zone_ids = {e.zone_id for e in events if e.zone_id is not None}
    cams = dict(db.execute(select(Camera.id, Camera.name).where(Camera.id.in_(cam_ids))).all()) if cam_ids else {}
    zones = dict(db.execute(select(Zone.id, Zone.name).where(Zone.id.in_(zone_ids))).all()) if zone_ids else {}

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for e in events:
        writer.writerow([
            e.id, csv_safe(cams.get(e.camera_id)), csv_safe(zones.get(e.zone_id)),
            csv_safe(e.anomaly_type), csv_safe(e.severity), csv_safe(e.decided_by),
            _local_iso(e.started_at), _local_iso(e.ended_at),
            "" if e.duration_ms is None else round(e.duration_ms / 1000, 1),
            e.confidence, csv_safe(e.status), csv_safe(e.fall_outcome),
            ";".join(str(t) for t in (e.track_ids or [])),
        ])
    stamp = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H%M")
    headers = {"Content-Disposition": f'attachment; filename="olaylar_{stamp}.csv"'}
    if truncated:
        headers["X-Truncated"] = "true"
    # BOM: Excel Turkce karakterleri UTF-8 olarak acsin
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/{event_id}", response_model=EventDetailOut)
def get_event(
    event_id: int, db: Session = Depends(get_db), mongo: Database = Depends(get_mongo),
    _: dict = Depends(current_user),
) -> EventDetailOut:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "olay bulunamadi")
    camera = db.get(Camera, event.camera_id)
    zone = db.get(Zone, event.zone_id) if event.zone_id is not None else None
    telemetry = mongo.telemetry.find_one({"event_id": event_id}, {"_id": False})
    return EventDetailOut(
        **EventOut.model_validate(event).model_dump(),
        camera_name=camera.name if camera else None,
        zone_name=zone.name if zone else None,
        telemetry=telemetry,
    )


@router.patch("/{event_id}", response_model=EventOut)
def update_event_status(
    event_id: int, body: EventStatusIn, db: Session = Depends(get_db),
    user: dict = Depends(require_role("operator", "admin")),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "olay bulunamadi")
    # 'new' hedef olamaz -- EventStatusIn'in Literal'i zaten bunu disliyor (SS9.5)
    event.status = body.status
    event.acked_by = user["id"]
    event.acked_at = datetime.datetime.now(datetime.timezone.utc)
    write_audit(db, user_id=user["id"], action="update_status", entity="event",
                entity_id=event_id, payload={"status": body.status})
    db.commit()
    db.refresh(event)
    return event


@router.get("/{event_id}/clip")
def get_event_clip(
    event_id: int, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> FileResponse:
    event = db.get(Event, event_id)
    if event is None or not event.clip_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "klip bulunamadi")
    path = _safe_storage_path(event.clip_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "klip dosyasi diskte yok")
    return FileResponse(path, media_type="video/mp4")


@router.get("/{event_id}/frame")
def get_event_frame(
    event_id: int, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> FileResponse:
    event = db.get(Event, event_id)
    if event is None or not event.frame_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kare bulunamadi")
    path = _safe_storage_path(event.frame_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kare dosyasi diskte yok")
    return FileResponse(path, media_type="image/jpeg")
