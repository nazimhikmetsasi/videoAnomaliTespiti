"""GET/PUT /api/settings, /api/settings/{camera_id} (ASAMA5_PLAN.md SS9.4).

Birlesim kurali: kamera satiri varsa o, yoksa global (camera_id IS NULL)
satiri doner -- panel "bu kamera globali mi kullaniyor" sorusunu `source`
alanindan, settings_client ise degisiklik olup olmadigini `updated_at`'tan
anlar (SS7).
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.audit import write_audit
from api.auth import current_user, require_role
from api.db.models import DetectionSettings
from api.db.postgres import get_db
from api.schemas import SettingsIn, SettingsOut, SettingsPatch

router = APIRouter()

_FIELDS = list(SettingsIn.model_fields)


def _to_out(row: DetectionSettings, source: str) -> SettingsOut:
    data = {f: getattr(row, f) for f in _FIELDS}
    return SettingsOut(**data, camera_id=row.camera_id, source=source, updated_at=row.updated_at)


def _get_global(db: Session) -> DetectionSettings:
    row = db.scalar(select(DetectionSettings).where(DetectionSettings.camera_id.is_(None)))
    if row is None:
        # init.sql her zaman bir global satir tohumlar; buraya dusmek kurulum hatasidir.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "global esik satiri yok")
    return row


@router.get("", response_model=SettingsOut)
def get_global_settings(db: Session = Depends(get_db), _: dict = Depends(current_user)) -> SettingsOut:
    return _to_out(_get_global(db), "global")


@router.get("/{camera_id}", response_model=SettingsOut)
def get_camera_settings(
    camera_id: int, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> SettingsOut:
    row = db.scalar(select(DetectionSettings).where(DetectionSettings.camera_id == camera_id))
    if row is not None:
        return _to_out(row, "camera")
    return _to_out(_get_global(db), "global")


@router.put("", response_model=SettingsOut)
def put_global_settings(
    body: SettingsPatch, db: Session = Depends(get_db), user: dict = Depends(require_role("admin")),
) -> SettingsOut:
    row = _get_global(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_by = user["id"]
    row.updated_at = datetime.datetime.now(datetime.timezone.utc)
    write_audit(db, user_id=user["id"], action="update", entity="detection_settings", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row, "global")


@router.put("/{camera_id}", response_model=SettingsOut)
def put_camera_settings(
    camera_id: int, body: SettingsPatch, db: Session = Depends(get_db),
    user: dict = Depends(require_role("admin")),
) -> SettingsOut:
    row = db.scalar(select(DetectionSettings).where(DetectionSettings.camera_id == camera_id))
    if row is None:
        # Yeni kamera satiri GLOBALDEN miras alir; sutun varsayilanlarina
        # birakilirsa global'de degistirilmis bir esik sessizce geri doner.
        base = _get_global(db)
        row = DetectionSettings(camera_id=camera_id,
                                **{f: getattr(base, f) for f in _FIELDS})
        db.add(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_by = user["id"]
    row.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.flush()
    write_audit(db, user_id=user["id"], action="upsert", entity="detection_settings", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row, "camera")
