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
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import current_user
from api.db.models import Camera, Event
from api.db.mongo import get_mongo
from api.db.postgres import get_db
from api.routers.cameras import resolve_camera_id
from api.schemas import CameraHealthOut

router = APIRouter()


# Siralama {camera_id:1, ts:-1} dizinine uyar: MongoDB tum belgeleri taramak
# yerine DISTINCT_SCAN kullanir (bir haftalik veride olculen 445 ms -> 1 ms).
_LATEST_PIPELINE = [
    {"$sort": {"camera_id": 1, "ts": -1}},
    {"$group": {"_id": "$camera_id", "doc": {"$first": "$$ROOT"}}},
]


def _latest_health_docs(mongo: Database) -> dict[str, dict]:
    """camera_health'teki her HAM camera_id degeri (ad ya da id metni) icin
    en son belge -- kamera basina ayri sorgu yerine tek aggregate (N+1 yok)."""
    return {row["_id"]: row["doc"] for row in mongo.camera_health.aggregate(_LATEST_PIPELINE)}


# Spark bir oturumu en az 2 adayla kabul eder (spark_min_hits); pencerede 20
# aday uretip hic olay uretemeyen kamera ya birbirinden uzak tek-aday gurultusu
# uretmistir ya da akis (Kafka / Spark) bozuktur. Olculmus bir sinir degil;
# 18'deki 24 saatlik kosunun verisiyle gozden gecirilecek.
STALL_MIN_CANDIDATES = 20
_STALE_SEC = 60.0   # bayat belge zaten "Bayat" gorunur, ayrica isaretlenmez
# Penceredeki saglik kayitlari en az bu kadar sure kapsamali. Olculdu: run_01
# saniyede ~4 aday uretiyor, 20'ye 5 sn'de ulasiyor; Spark'in ilk olayi ~7.5
# sn sonra geliyor. Bu sart olmadan her kamera acilisinda birkac saniye
# yanlis "aday var, olay yok" gorunuyordu.
MIN_SPAN_SEC = 60.0


def pulse(cand_first: int | None, cand_last: int | None, events: int,
          age_sec: float | None, span_sec: float = MIN_SPAN_SEC) -> tuple[int | None, bool]:
    """(candidates_window, stalled). Sayac birikimlidir; surec yeniden
    baslayinca sifirlanir (son < ilk) -- o zaman son, sifirdan beri uretilen
    adaydir. Belge ya da alan yoksa None ve stalled False. span_sec: penceredeki
    ilk ve son saglik kaydi arasi sure."""
    if cand_first is None or cand_last is None:
        return None, False
    cands = cand_last - cand_first if cand_last >= cand_first else cand_last
    stalled = (cands >= STALL_MIN_CANDIDATES and events == 0
               and age_sec is not None and age_sec <= _STALE_SEC
               and span_sec >= MIN_SPAN_SEC)
    return cands, stalled


def _window_candidates(mongo: Database, since: datetime.datetime) -> dict[str, tuple]:
    """Ham camera_id -> (ilk, son, kapsanan sn) birikimli aday sayaci, pencere icinde."""
    pipeline = [
        {"$match": {"ts": {"$gte": since}}},
        {"$sort": {"camera_id": 1, "ts": 1}},
        {"$group": {"_id": "$camera_id", "first": {"$first": "$candidates"},
                    "last": {"$last": "$candidates"},
                    "first_ts": {"$first": "$ts"}, "last_ts": {"$last": "$ts"}}},
    ]
    out = {}
    for r in mongo.camera_health.aggregate(pipeline):
        span = (r["last_ts"] - r["first_ts"]).total_seconds()
        out[r["_id"]] = (r.get("first"), r.get("last"), span)
    return out


def _to_health_out(cam: Camera, doc: dict | None, now: datetime.datetime,
                   window_min: int = 10, cands: tuple | None = None,
                   events: int = 0) -> CameraHealthOut:
    if doc is None:
        # Mongo kaydi olmayan kamera da listede kalir, olcum alanlari null --
        # panelin "Baglanti Yok" durumu.
        return CameraHealthOut(camera_id=cam.id, name=cam.name,
                               window_min=window_min, events_window=events)
    ts = doc["ts"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    age_sec = (now - ts).total_seconds()
    first, last, span = cands or (None, None, 0.0)
    cand_win, stalled = pulse(first, last, events, age_sec, span)
    return CameraHealthOut(
        window_min=window_min, candidates_window=cand_win,
        events_window=events, stalled=stalled,
        camera_id=cam.id, name=cam.name,
        fps_actual=doc.get("fps_actual"), dropped=doc.get("dropped"),
        infer_ms=doc.get("infer_ms"), gpu_mem=doc.get("gpu_mem"),
        queue_depth=doc.get("queue_depth"), ws_port=doc.get("ws_port"),
        candidates=doc.get("candidates"),
        # Belgenin yasi -- panel bayat veriyi canli sanmasin.
        age_sec=age_sec,
    )


@router.get("/cameras", response_model=list[CameraHealthOut])
def cameras_health(
    # Annotated: Query() varsayilan olarak yazilsa fonksiyon dogrudan
    # cagrilinca (testler) Query nesnesi gelirdi.
    window_min: Annotated[int, Query(ge=1, le=60)] = 10,
    db: Session = Depends(get_db), mongo: Database = Depends(get_mongo),
    _: dict = Depends(current_user),
) -> list[CameraHealthOut]:
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(minutes=window_min)
    cams = list(db.scalars(select(Camera).order_by(Camera.id)))
    by_raw_id = _latest_health_docs(mongo)
    events_by_cam = dict(db.execute(
        select(Event.camera_id, func.count()).where(Event.started_at >= since)
        .group_by(Event.camera_id)
    ).all())
    cands_by_raw = _window_candidates(mongo, since)

    # Ham camera_id (ad veya id metni) -> gercek kamera id'sine coz. Ayni
    # cozum vision/'in kullandigi ile (api/routers/cameras.py) -- ikinci
    # bir ad-veya-id sorgusu yazilmaz.
    by_camera_id: dict[int, dict] = {}
    cands_by_camera: dict[int, tuple] = {}
    for raw_id, doc in by_raw_id.items():
        resolved = resolve_camera_id(db, raw_id)
        if resolved is not None:
            by_camera_id[resolved] = doc
            if raw_id in cands_by_raw:
                cands_by_camera[resolved] = cands_by_raw[raw_id]

    return [
        _to_health_out(cam, by_camera_id.get(cam.id), now, window_min,
                       cands_by_camera.get(cam.id), events_by_cam.get(cam.id, 0))
        for cam in cams
    ]
