"""POST/GET /api/evidence (docs/ASAMA6_PLAN.md SS8.1/8.2).

Kanit-olay eslesmesi IKI YONLUDUR ve sira garantisi yoktur (vision/ kaniti
epizot biter bitmez gonderir, olay satiri ise Spark gecikmesinden sonra
dogar):

  yon 1 (bu dosya):                 kanit gelince -- eslesen olay aranir
  yon 2 (api/workers/consumer.py):  olay eklenirken -- bekleyen kanit aranir

Ikisi de ayni dogal anahtari (camera_id, anomaly_type) ve ayni toleransi
kullanir; tolerans api/matching.py'de tek yerde durur ve spark_window_sec'ten
gelir.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from api.auth import current_user, require_role
from api.db.models import Event, Evidence
from api.db.mongo import get_mongo, link_pose_sequence
from api.db.postgres import get_db
from api.matching import tolerance
from api.schemas import EvidenceIn, EvidenceMatchOut, EvidenceOut

router = APIRouter()


def _resolve_camera_id(db: Session, raw: str) -> int | None:
    """Kafka tuketicisindeki (api/workers/consumer.py CameraCache) ayni cozum:
    sayisal id veya kamera adi kabul edilir."""
    row = db.execute(
        text("SELECT id FROM cameras WHERE id::text = :cid OR name = :cid"),
        {"cid": raw},
    ).first()
    return row[0] if row else None


def _find_matching_event(db: Session, camera_id: int, anomaly_type: str,
                          start_dt: datetime.datetime) -> Event | None:
    """Yon 1: (camera_id, anomaly_type) ayni ve baslangic tolerans icinde olan
    olay satirini arar. Saf ORM sorgusu -- DB'siz testte db.scalar() sahtesiyle
    calisir (tests/test_evidence_match.py).

    Iki eleme aday coklugu icindir: ZATEN bir kanida bagli olay atlanir (yoksa
    iki epizot ayni satiri paylasir), kalanlardan da EN YAKINI secilir --
    siralamasiz sorgu tolerans icindeki herhangi birini dondururdu."""
    tol = tolerance()
    lo, hi = start_dt - tol, start_dt + tol
    already_bound = select(Evidence.id).where(Evidence.event_id == Event.id).exists()
    return db.scalar(
        select(Event)
        .where(
            Event.camera_id == camera_id,
            Event.anomaly_type == anomaly_type,
            Event.started_at >= lo,
            Event.started_at <= hi,
            ~already_bound,
        )
        .order_by(func.abs(func.extract("epoch", Event.started_at - start_dt)))
        .limit(1)
    )


@router.post("", response_model=EvidenceMatchOut, status_code=status.HTTP_201_CREATED)
def create_evidence(
    body: EvidenceIn, db: Session = Depends(get_db), mongo: Database = Depends(get_mongo),
    _: dict = Depends(require_role("admin", "operator")),
) -> EvidenceMatchOut:
    camera_id = _resolve_camera_id(db, body.camera_id)
    if camera_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kamera bulunamadi")

    start_dt = datetime.datetime.fromtimestamp(body.start_time, tz=datetime.timezone.utc)
    end_dt = (datetime.datetime.fromtimestamp(body.end_time, tz=datetime.timezone.utc)
              if body.end_time is not None else None)

    # evidence satiri HER DURUMDA yazilir, eslesse de eslesmese de. Eslesince
    # satiri atlamak clip_truncated'i tamamen kaybederdi -- SS5.2 klibin
    # kirpildiginin bildirilmesini sart kosuyor ve events tablosunda o kolon
    # yok. Satir ayrica kanit uretiminin tam defterini tutar (SS12 olcum 5).
    row = Evidence(
        camera_id=camera_id, anomaly_type=body.anomaly_type, track_key=body.track_key,
        started_at=start_dt, ended_at=end_dt, frame_path=body.frame_path,
        clip_path=body.clip_path, clip_truncated=body.clip_truncated, mongo_ref=body.mongo_ref,
    )
    db.add(row)

    event = _find_matching_event(db, camera_id, body.anomaly_type, start_dt)
    event_id = None
    if event is not None:
        # SS8.2 madde 1: kanit alanlari olaya yazilir, satir olaya baglanir.
        if body.frame_path:
            event.frame_path = body.frame_path
        if body.clip_path:
            event.clip_path = body.clip_path
        if body.mongo_ref:
            event.mongo_ref = body.mongo_ref
        event_id = event.id   # commit sonrasi ORM nesnesi expire olur
        row.event_id = event_id

    db.commit()
    db.refresh(row)
    # SS8.2 madde 2: eslesmeyen satir SILINMEZ, event_id NULL kalir ve
    # GET /api/evidence?unmatched=true ile gorunur olur.
    if event_id is None:
        return EvidenceMatchOut(matched=False, evidence_id=row.id)
    link_pose_sequence(mongo, body.mongo_ref, event_id)
    return EvidenceMatchOut(matched=True, event_id=event_id, evidence_id=row.id)


@router.get("", response_model=list[EvidenceOut])
def list_evidence(
    unmatched: bool = False, db: Session = Depends(get_db), _: dict = Depends(current_user),
) -> list[Evidence]:
    stmt = select(Evidence).order_by(Evidence.started_at.desc())
    if unmatched:
        stmt = stmt.where(Evidence.event_id.is_(None))
    return list(db.scalars(stmt))
