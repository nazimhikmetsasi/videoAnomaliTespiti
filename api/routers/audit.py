"""GET /api/audit -- denetim kaydi listesi (ASAMA8_PLAN.md SS3.8.2).

Dosya adi bilerek `audit.py` degil `routers/audit.py`: api/audit.py'deki
write_audit yardimcisi ile karismasin.

Yalniz admin okur. Kullanici adi icin users LEFT JOIN -- audit_log.user_id
ON DELETE SET NULL oldugu icin NULL olabilir (kullanici silinmis/pasif ya
da sistem eylemi), INNER JOIN o satirlari listeden dusururdu.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from api.auth import require_role
from api.db.models import AuditLog, User
from api.db.postgres import get_db
from api.schemas import AuditListOut, AuditOut

router = APIRouter()


def _filters(
    user_id: int | None, action: str | None, entity: str | None,
    from_: datetime.datetime | None, to: datetime.datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if action is not None:
        filters.append(AuditLog.action == action)
    if entity is not None:
        filters.append(AuditLog.entity == entity)
    if from_ is not None:
        filters.append(AuditLog.created_at >= from_)
    if to is not None:
        filters.append(AuditLog.created_at <= to)
    return filters


@router.get("", response_model=AuditListOut)
def list_audit(
    user_id: int | None = None,
    action: str | None = None,
    entity: str | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: dict = Depends(require_role("admin")),
) -> AuditListOut:
    limit = min(max(limit, 1), 500)   # events.py'deki tavanla ayni (SS9.5)
    filters = _filters(user_id, action, entity, from_, to)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = db.execute(
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .limit(limit).offset(offset)
    ).all()
    items = [
        AuditOut(
            id=log.id, user_id=log.user_id, username=username, action=log.action,
            entity=log.entity, entity_id=log.entity_id, payload=log.payload,
            ip=log.ip, created_at=log.created_at,
        )
        for log, username in rows
    ]
    return AuditListOut(total=total, items=items)
