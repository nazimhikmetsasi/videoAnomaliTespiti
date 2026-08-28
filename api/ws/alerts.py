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
from sqlalchemy import text

from api.auth import decode_token
from api.config import KAFKA_BOOTSTRAP
from api.db.postgres import SessionLocal
from api.ws.manager import ConnectionManager

router = APIRouter()
manager = ConnectionManager()

TOPIC = "anomaly-events"
GROUP_ID = "anomaly-ws-alerts"


@router.websocket("/ws/alerts")
async def alerts_ws(ws: WebSocket, token: str | None = None) -> None:
    """Jeton `?token=<JWT>` ile gelir -- WebSocket el sikismasinda Authorization
    basligi yoktur. Kimliksiz yayin kabul edilmez: alarm govdesi kamera adini
    ve olay ayrintisini tasir (SS3'un gorü akisi icin koydugu ayni olcut)."""
    if decode_token(token) is None:
        # 1008'in istemciye ulasmasi icin once accept gerekir; Starlette
        # accept'siz close'u HTTP reddine cevirir ve kod kaybolur. Veri
        # gonderilmeden kapatildigi icin acilis zararsizdir.
        await ws.accept()
        await ws.close(code=1008, reason="gecersiz jeton")
        return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # istemciden veri beklenmez, kopmayi yakalamak icin bekler
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
        consumer.subscribe([TOPIC])
        try:
            while not self._stop.is_set():
                msg = consumer.poll(1.0)
                if msg is None or msg.error():
                    continue
                try:
                    body = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                    continue
                payload = {**body, "camera_name": _camera_name(body.get("camera_id"))}
                if self._loop is not None:
                    asyncio.run_coroutine_threadsafe(self._manager.broadcast(payload), self._loop)
        finally:
            consumer.close()


broadcaster = AlertBroadcaster(manager)
