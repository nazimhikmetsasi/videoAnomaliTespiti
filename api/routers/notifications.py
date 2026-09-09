"""GET /api/notifications -- bildirim teslim kaydi (ASAMA8_PLAN.md SS3.8.3).

Panelin "Denetim Kaydi" ekraninin Bildirimler sekmesi bu ucu okur. Tablo
Asama 7'den beri doluyor (api/notify.py telegram gonderiminden sonra satir
yaziyor) ama okuyan uc yoktu -- 8.3'te ekran baglanirken fark edildi.

Olay bilgisi icin events LEFT JOIN degil INNER JOIN yeterliydi (event_id
NOT NULL + ON DELETE CASCADE), yine de LEFT JOIN kullaniliyor: olay
silinmis bir bildirim satirini listeden dusurmek yerine gostermek denetim
amacina daha uygun.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from api.auth import require_role
from api.db.models import Camera, Event, Notification
from api.db.postgres import get_db
from api.schemas import NotificationListOut, NotificationOut

router = APIRouter()


def _filters(
    channel: str | None, status: str | None,
    from_: datetime.datetime | None, to: datetime.datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if channel is not None:
        filters.append(Notification.channel == channel)
    if status is not None:
        filters.append(Notification.status == status)
    if from_ is not None:
        filters.append(Notification.sent_at >= from_)
    if to is not None:
        filters.append(Notification.sent_at <= to)
    return filters


@router.get("", response_model=NotificationListOut)
def list_notifications(
    channel: str | None = None,
    status: str | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: dict = Depends(require_role("admin")),
) -> NotificationListOut:
    limit = min(max(limit, 1), 500)   # audit/events ile ayni tavan
    filters = _filters(channel, status, from_, to)

    total = db.scalar(select(func.count()).select_from(Notification).where(*filters)) or 0
    rows = db.execute(
        select(Notification, Event.anomaly_type, Camera.name)
        .outerjoin(Event, Event.id == Notification.event_id)
        .outerjoin(Camera, Camera.id == Event.camera_id)
        .where(*filters)
        .order_by(Notification.sent_at.desc())
        .limit(limit).offset(offset)
    ).all()
    items = [
        NotificationOut(
            id=n.id, event_id=n.event_id, anomaly_type=anomaly_type, camera_name=camera_name,
            channel=n.channel, target=n.target, status=n.status, error=n.error, sent_at=n.sent_at,
        )
        for n, anomaly_type, camera_name in rows
    ]
    return NotificationListOut(total=total, items=items)
