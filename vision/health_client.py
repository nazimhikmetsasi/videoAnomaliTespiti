"""Kalp atisi: `PATCH /api/cameras/{id}/heartbeat` + MongoDB `camera_health`
belgesi (ASAMA6_PLAN.md SS7). `vision/settings_client.py` ile AYNI desen:
arka plan daemon thread, hicbir istisna disari sizmaz, goru dongusu asla
bloklanmaz -- hata sayilir, yutulur.
"""

from __future__ import annotations

import datetime
import threading

import httpx
import torch

from vision.evidence import MONGO_DB, default_mongo_url  # noqa: F401 (yeniden disari acilir)
from vision.source import VideoSource


class HealthClient:
    def __init__(self, base_url: str, camera_id: str, source: VideoSource, *,
                 interval: float = 5.0, token: str | None = None,
                 mongo_url: str = "", ws_port: int | None = None) -> None:
        self._url = f"{base_url.rstrip('/')}/api/cameras/{camera_id}/heartbeat"
        self._camera_id = camera_id
        self._source = source
        self._interval = interval
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._mongo_url = mongo_url
        self._mongo = None
        # StreamServer gercekten acikken gercek port, kapaliyken None --
        # panel bagli olmayan bir porta baglanmaya calismasin (ASAMA8_PLAN.md
        # 8.6 SS3, madde 2).
        self._ws_port = ws_port

        self._fps_actual = 0.0
        self._infer_ms = 0.0
        self.sent = 0
        self.failures = 0
        self.last_error = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def note(self, fps: float, infer_ms: float) -> None:
        """run.py her karede besler; en son deger sonraki atimda kullanilir."""
        self._fps_actual, self._infer_ms = fps, infer_ms

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="health-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._beat_once()
            self._stop.wait(self._interval)

    def _beat_once(self) -> None:
        try:
            resp = httpx.patch(self._url, json={"status": "online"},
                                headers=self._headers, timeout=5.0)
            resp.raise_for_status()
            self.sent += 1
        except httpx.HTTPError as exc:
            self.failures += 1
            self.last_error = f"heartbeat: {exc}"
        self._write_health()

    def _write_health(self) -> None:
        if not self._mongo_url:
            return
        gpu_mem = int(torch.cuda.memory_reserved()) if torch.cuda.is_available() else 0
        try:
            if self._mongo is None:
                from pymongo import MongoClient
                self._mongo = MongoClient(self._mongo_url)
            db = self._mongo[MONGO_DB]
            db.camera_health.insert_one({
                # BSON Date olmali, float epoch DEGIL: infra/mongo/init.js
                # camera_health.ts uzerine 7 gunluk TTL indeksi koyuyor ve
                # MongoDB TTL'i yalnizca Date alaninda calisir.
                "camera_id": self._camera_id,
                "ts": datetime.datetime.now(datetime.timezone.utc),
                "fps_actual": self._fps_actual,
                "dropped": self._source.frames_dropped,
                "infer_ms": self._infer_ms, "gpu_mem": gpu_mem,
                "ws_port": self._ws_port,
                # ponytail: VideoSource kuyruk derinligini disari acmiyor (Asama 6
                # kapsami disinda), dogrudan ic alana bakiliyor. Kamu API'si
                # gerekirse `VideoSource.queue_depth` property'si eklenir.
                "queue_depth": self._source._queue.qsize(),
            })
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            self.last_error = f"mongo health: {exc}"
