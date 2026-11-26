"""Kirmizi alarm yayini: /ws/alerts + anomaly-events'i IKINCI KEZ okuyan
Kafka tuketicisi (docs/ASAMA6_PLAN.md SS8.4).

Neden ikinci tuketici: api/workers/consumer.py ayri bir container'dir (farkli
process). Aralarina Redis pub/sub gibi yeni bir kanal icat etmek yerine
ZATEN VAR OLAN anomaly-events topic'i farkli bir group.id ile tekrar okunur --
iki tuketici birbirinin offset'ini bozmaz.

Alarm WS'i veritabani yazimini beklemez (ayni mesaji consumer.py'den bagimsiz
bir offset'ten okur); panel olay detayini GET /api/events ile ayrica ceker.
"""

from __future__ import annotations

import asyncio
import json
import threading

from confluent_kafka import Consumer
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from api.auth import active_user_for_token
from api.config import KAFKA_BOOTSTRAP
from api.db.postgres import SessionLocal
from api.ws.manager import ConnectionManager

router = APIRouter()
manager = ConnectionManager()

TOPIC = "anomaly-events"
OUTCOME_TOPIC = "fall-outcomes"   # ayni deger api/workers/consumer.py'de; o modulu import etmemek icin tekrar
GROUP_ID = "anomaly-ws-alerts"
REVALIDATE_SEC = 60   # pasiflestirilen kullanicinin acik baglantisi en gec bu surede kapanir


def _token_active(token: str | None) -> bool:
    # ayri oturum: WS suresince istek bagimli get_db oturumu tutulmaz
    with SessionLocal() as db:
        return active_user_for_token(db, token) is not None


@router.websocket("/ws/alerts")
async def alerts_ws(ws: WebSocket, token: str | None = None) -> None:
    """Jeton `?token=<JWT>` ile gelir -- WebSocket el sikismasinda Authorization
    basligi yoktur. Kimliksiz yayin kabul edilmez: alarm govdesi kamera adini
    ve olay ayrintisini tasir (SS3'un gorü akisi icin koydugu ayni olcut)."""
    if not await run_in_threadpool(_token_active, token):
        # 1008'in istemciye ulasmasi icin once accept gerekir; Starlette
        # accept'siz close'u HTTP reddine cevirir ve kod kaybolur. Veri
        # gonderilmeden kapatildigi icin acilis zararsizdir.
        await ws.accept()
        await ws.close(code=1008, reason="gecersiz jeton")
        return
    await manager.connect(ws)
    try:
        while True:
            try:
                # istemciden veri beklenmez; kopmayi yakalar, zaman asimi yeniden denetim tetikler
                await asyncio.wait_for(ws.receive_text(), REVALIDATE_SEC)
            except asyncio.TimeoutError:
                if not await run_in_threadpool(_token_active, token):
                    await ws.close(code=1008, reason="oturum gecersiz")
                    return
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


def _camera_name(raw_camera_id: object) -> str | None:
    """SS8.4: govdeye camera_name eklenir -- consumer.py'deki CameraCache
    cozumuyle AYNI sorgu (id::text = :cid OR name = :cid). Alarm seyrek
    oldugu icin onbellege gerek yok."""
    if raw_camera_id is None:
        return None
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT name FROM cameras WHERE id::text = :cid OR name = :cid"),
            {"cid": str(raw_camera_id)},
        ).first()
    return row[0] if row else None


def outcome_alert(msg: object, camera_name: str | None) -> dict | None:
    """fall-outcomes mesaji -> panel govdesi (13.6 SS3). `unknown` panele
    gitmez (operatore soylenecek bir sey yok); bozuk mesaj None."""
    if not isinstance(msg, dict) or msg.get("outcome") not in ("down", "recovered"):
        return None
    track_id, fall_time = msg.get("track_id"), msg.get("fall_time")
    if (msg.get("camera_id") in (None, "") or isinstance(track_id, bool)
            or not isinstance(track_id, int) or isinstance(fall_time, bool)
            or not isinstance(fall_time, (int, float))):
        return None
    metrics = msg.get("metrics")
    return {
        "kind": "fall_outcome", "camera_id": msg["camera_id"], "camera_name": camera_name,
        "track_id": track_id, "fall_time": float(fall_time), "outcome": msg["outcome"],
        "metrics": metrics if isinstance(metrics, dict) else {},
    }


class AlertBroadcaster:
    """anomaly-events'i AYRI bir is parcaciginda tuketir (confluent-kafka
    senkrondur, FastAPI'nin asyncio dongusunu bloklamamali) ve
    run_coroutine_threadsafe ile manager.broadcast'e devreder."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        # get_event_loop() degil: 3.12'de DeprecationWarning, 3.14'te hata.
        # start() lifespan icinden, calisan dongunun icinden cagrilir.
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": GROUP_ID,
            # "latest": alarm yayini yalnizca YENI olaylar icindir; "earliest"
            # olsaydi her API yeniden baslatmasinda gecmis alarmlar tekrar basardi.
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        consumer.subscribe([TOPIC, OUTCOME_TOPIC])
        try:
            while not self._stop.is_set():
                msg = consumer.poll(1.0)
                if msg is None or msg.error():
                    continue
                try:
                    body = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                    continue
                if not isinstance(body, dict):
                    continue
                if msg.topic() == OUTCOME_TOPIC:
                    payload = outcome_alert(body, _camera_name(body.get("camera_id")))
                    if payload is None:
                        continue
                else:
                    payload = {**body, "camera_name": _camera_name(body.get("camera_id"))}
                if self._loop is not None:
                    asyncio.run_coroutine_threadsafe(self._manager.broadcast(payload), self._loop)
        finally:
            consumer.close()


broadcaster = AlertBroadcaster(manager)
