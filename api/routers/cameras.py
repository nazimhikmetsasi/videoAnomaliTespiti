"""GET/POST/PUT/DELETE /api/cameras, PATCH /heartbeat (ASAMA5_PLAN.md SS9.2)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api.audit import write_audit
from api.auth import current_user, require_role
from api.db.models import Camera
from api.db.postgres import get_db
from api.schemas import CameraHeartbeatIn, CameraIn, CameraOut

router = APIRouter()


def resolve_camera_id(db: Session, raw: str) -> int | None:
    """Sayisal id VEYA kamera adi kabul eder.

    `vision/` kamerayi ADIYLA tanir (klip dosya adi / webcam indeksi), panel
    ise sayisal id ile. Kafka tuketicisi (CameraCache) ve POST /api/evidence
    zaten bu cozumu kullaniyor; ucuncu kopyayi acmamak icin tek yer burasi."""
    row = db.execute(
        text("SELECT id FROM cameras WHERE id::text = :cid OR name = :cid"),
        {"cid": raw},
    ).first()
    return row[0] if row else None


def _get_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kamera bulunamadi")
    return cam


@router.get("", response_model=list[CameraOut])
def list_cameras(
    is_active: bool | None = None, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> list[Camera]:
    stmt = select(Camera).order_by(Camera.id)
    if is_active is not None:
        stmt = stmt.where(Camera.is_active == is_active)
    return list(db.scalars(stmt))


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: int, db: Session = Depends(get_db), _: dict = Depends(current_user)) -> Camera:
    return _get_or_404(db, camera_id)


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(
    body: CameraIn, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> Camera:
    cam = Camera(**body.model_dump())
    db.add(cam)
    db.flush()
    write_audit(db, user_id=user["id"], action="create", entity="camera", entity_id=cam.id)
    db.commit()
    db.refresh(cam)
    return cam


@router.put("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: int, body: CameraIn, db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
) -> Camera:
    cam = _get_or_404(db, camera_id)
    for field, value in body.model_dump().items():
        setattr(cam, field, value)
    write_audit(db, user_id=user["id"], action="update", entity="camera", entity_id=camera_id)
    db.commit()
    db.refresh(cam)
    return cam


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: int, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> None:
    cam = _get_or_404(db, camera_id)
    db.delete(cam)
    write_audit(db, user_id=user["id"], action="delete", entity="camera", entity_id=camera_id)
    db.commit()


@router.patch("/{camera_id}/heartbeat", response_model=CameraOut)
def heartbeat(
    camera_id: str, body: CameraHeartbeatIn, db: Session = Depends(get_db),
    _: dict = Depends(current_user),
) -> Camera:
    # Kimlik ister -- JWT'siz herkes kamera durumunu degistiremesin.
    # camera_id METIN: vision/ kamerayi adiyla cagirir ("zone_01"), int
    # bekleyen surum her kalp atisina 422 donuyordu ve cameras.status hic
    # guncellenmiyordu (Asama 6 olcumunde yakalandi).
    resolved = resolve_camera_id(db, camera_id)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kamera bulunamadi")
    cam = _get_or_404(db, resolved)
    cam.status = body.status
    cam.last_seen_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(cam)
    return cam
