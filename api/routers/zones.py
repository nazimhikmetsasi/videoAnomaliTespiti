"""GET/POST/PUT/DELETE /api/zones (ASAMA5_PLAN.md SS9.3).

Poligon ve direction_vector dogrulamasi burada YOK -- tek yer schemas.py'deki
ZoneIn validator'lari (v1'de bu doubling zone_01 yanlis pozitiflerinin
kaynagiydi, bkz. docs/DURUM.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.audit import write_audit
from api.auth import current_user, require_role
from api.db.models import Zone
from api.db.postgres import get_db
from api.schemas import ZoneIn, ZoneOut

router = APIRouter()


def _get_or_404(db: Session, zone_id: int) -> Zone:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bolge bulunamadi")
    return zone


@router.get("", response_model=list[ZoneOut])
def list_zones(
    camera_id: int | None = None, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> list[Zone]:
    stmt = select(Zone).order_by(Zone.id)
    if camera_id is not None:
        stmt = stmt.where(Zone.camera_id == camera_id)
    return list(db.scalars(stmt))


@router.post("", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(
    body: ZoneIn, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> Zone:
    zone = Zone(**body.model_dump(), created_by=user["id"])
    db.add(zone)
    db.flush()
    write_audit(db, user_id=user["id"], action="create", entity="zone", entity_id=zone.id)
    db.commit()
    db.refresh(zone)
    return zone


@router.put("/{zone_id}", response_model=ZoneOut)
def update_zone(
    zone_id: int, body: ZoneIn, db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
) -> Zone:
    zone = _get_or_404(db, zone_id)
    for field, value in body.model_dump().items():
        setattr(zone, field, value)
    write_audit(db, user_id=user["id"], action="update", entity="zone", entity_id=zone_id)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    zone_id: int, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> None:
    zone = _get_or_404(db, zone_id)
    db.delete(zone)
    write_audit(db, user_id=user["id"], action="delete", entity="zone", entity_id=zone_id)
    db.commit()
