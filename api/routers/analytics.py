"""GET /api/analytics/summary, /api/analytics/ablation (ASAMA5_PLAN.md SS9.6)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from api.auth import current_user
from api.db.models import Camera, Event
from api.db.postgres import get_db
from api.schemas import AnalyticsSummaryOut

router = APIRouter()


def _filters(
    camera_id: int | None, from_: datetime.datetime | None, to: datetime.datetime | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if camera_id is not None:
        filters.append(Event.camera_id == camera_id)
    if from_ is not None:
        filters.append(Event.started_at >= from_)
    if to is not None:
        filters.append(Event.started_at <= to)
    return filters


@router.get("/summary", response_model=AnalyticsSummaryOut)
def summary(
    camera_id: int | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    _: dict = Depends(current_user),
) -> AnalyticsSummaryOut:
    filters = _filters(camera_id, from_, to)
    total = db.scalar(select(func.count()).select_from(Event).where(*filters)) or 0

    def _grouped(col: ColumnElement) -> list[dict]:
        rows = db.execute(select(col, func.count()).where(*filters).group_by(col)).all()
        return [{col.key: k, "count": c} for k, c in rows]

    by_camera_rows = db.execute(
        select(Event.camera_id, Camera.name, func.count())
        .join(Camera, Camera.id == Event.camera_id)
        .where(*filters)
        .group_by(Event.camera_id, Camera.name)
    ).all()

    # Recharts'in dogrudan tuketecegi bicim (SS9.6).
    hour = func.date_trunc("hour", Event.started_at)
    by_hour_rows = db.execute(select(hour, func.count()).where(*filters).group_by(hour).order_by(hour)).all()

    return AnalyticsSummaryOut(
        total=total,
        by_type=_grouped(Event.anomaly_type),
        by_severity=_grouped(Event.severity),
        by_status=_grouped(Event.status),
        by_camera=[{"camera_id": cid, "name": name, "count": c} for cid, name, c in by_camera_rows],
        by_hour=[{"hour": h, "count": c} for h, c in by_hour_rows],
    )


@router.get("/ablation")
def ablation(
    camera_id: int | None = None,
    from_: datetime.datetime | None = Query(None, alias="from"),
    to: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    _: dict = Depends(current_user),
) -> list[dict]:
    # decided_by x anomaly_type x status kirilimi -- tum satirlar bugun 'rule',
    # Asama 9'dan sonra anlamlanir (SS9.6).
    filters = _filters(camera_id, from_, to)
    rows = db.execute(
        select(Event.decided_by, Event.anomaly_type, Event.status, func.count())
        .where(*filters)
        .group_by(Event.decided_by, Event.anomaly_type, Event.status)
    ).all()
    return [{"decided_by": d, "anomaly_type": t, "status": s, "count": c} for d, t, s, c in rows]
