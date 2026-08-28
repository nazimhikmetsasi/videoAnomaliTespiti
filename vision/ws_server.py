"""Canli goru WebSocket sunucusu: /ws/live/{camera_id} ikili JPEG,
/ws/meta/{camera_id} JSON (ASAMA6_PLAN.md SS3).

Kendi asyncio dongusunu ayri bir daemon thread'de calistirir -- ana goru
dongusu asla bloklanmaz. `publish_frame`/`publish_meta` kamera basina TEK
elemanli "son deger kazanir" bir kutuya yazar; yayin tarafi bu kutuyu kisa
araliklarla yoklar (polling). Kuyruk yok: yavas istemci kare biriktirmez,
`vision/source.py`'nin canli kaynak kuralinin (en yeni kare kazanir) ayni
tasarimi.

Kimlik dogrulama: `?token=<JWT>` sorgu parametresi, api/auth.py ile AYNI
JWT_SECRET + HS256 kullanilarak YEREL dogrulanir -- veritabanina gidilmez
(goru hatti API'ye bagimli olmamali). JWT_SECRET yoksa `start()` sunucuyu
ACMAZ, tek satir uyari basar -- kimliksiz yayin yok.
"""

from __future__ import annotations

import asyncio
import json
import threading
from urllib.parse import parse_qs, urlparse

import jwt
import websockets
from websockets.exceptions import ConnectionClosed

ALGORITHM = "HS256"
# ponytail: event-driven (asyncio.Condition) daha az CPU yakardi; 5 ms yoklama
# 25 FPS'lik (40 ms) kare hizinin sekizde biri, yeterince sik ve basit.
POLL_SEC = 0.005


class _Box:
    """Kamera basina "son deger kazanir" kutusu. `seq` degisince yeni veri var demektir.

    `data` kare icin `bytes` (BINARY WS cercevesi), meta icin `str` (TEXT WS
    cercevesi) tasir. `websockets` tip'e gore cerceveyi kendisi secer --
    meta'yi bytes olarak gondermek tarayicida `event.data` Blob/ArrayBuffer
    yapar, `JSON.parse` once `.text()` ister; `str` dogrudan calisir."""

    __slots__ = ("data", "seq")

    def __init__(self) -> None:
        self.data: bytes | str | None = None
        self.seq = 0


class StreamServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8001,
                 jwt_secret: str | None = None) -> None:
        self.host = host
        self.port = port
        self._jwt_secret = jwt_secret
        self.opened = False

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event: asyncio.Event | None = None

        self._lock = threading.Lock()
        self._frames: dict[str, _Box] = {}
        self._meta: dict[str, _Box] = {}
        # AYRI sayilir: /ws/meta'ya bagli bir istemci JPEG kodlamasini
        # BASLATMAMALI (SS3, SS12 olcum 3). Tek sayacla panel yalnizca meta
        # dinlerken de her kare kodlanirdi.
        self._counts = {"live": 0, "meta": 0}

    def start(self) -> None:
        """Arka plan daemon thread -- ana goru dongusunu bloklamaz."""
        if not self._jwt_secret:
            print("  [ws_server] JWT_SECRET yok -- WebSocket sunucusu ACILMADI (kimliksiz yayin yasak)")
            return
        self._thread = threading.Thread(target=self._run_loop, name="ws-server", daemon=True)
        self._thread.start()
        self.opened = True

    def stop(self) -> None:
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    # --- uretici tarafi (goru dongusu bu iki metodu cagirir) -------------

    def publish_frame(self, camera_id: str, jpeg: bytes) -> None:
        with self._lock:
            box = self._frames.setdefault(camera_id, _Box())
            box.data = jpeg
            box.seq += 1

    def publish_meta(self, camera_id: str, meta: dict) -> None:
        body = json.dumps(meta)   # str -> TEXT WS cercevesi (bkz. _Box docstring)
        with self._lock:
            box = self._meta.setdefault(camera_id, _Box())
            box.data = body
            box.seq += 1

    @property
    def live_clients(self) -> int:
        """/ws/live'a bagli istemci sayisi -- JPEG kodlamasinin kapisi budur.
        Bu asamada sunucu tek kamerayla calistirilir (ASAMA6_PLAN.md SS13);
        toplam sayim o kameranin istemci sayisidir."""
        with self._lock:
            return self._counts["live"]

    @property
    def meta_clients(self) -> int:
        """/ws/meta'ya bagli istemci sayisi. Meta gövdesinin kurulmasi ve
        json.dumps'i de bedavaya gelmez (her karede N iz x 17 nokta), o yuzden
        dinleyen yokken o is de hic yapilmaz."""
        with self._lock:
            return self._counts["meta"]

    # --- asyncio tarafi ----------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        async with websockets.serve(self._handler, self.host, self.port):
            await self._stop_event.wait()

    def _valid_token(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            jwt.decode(token, self._jwt_secret, algorithms=[ALGORITHM])
            return True
        except jwt.PyJWTError:
            return False

    async def _handler(self, connection) -> None:
        parsed = urlparse(connection.request.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 3 or parts[0] != "ws" or parts[1] not in ("live", "meta"):
            await connection.close(1008, "gecersiz yol")
            return
        kind, camera_id = parts[1], parts[2]
        token = parse_qs(parsed.query).get("token", [None])[0]
        if not self._valid_token(token):
            await connection.close(1008, "jeton gecersiz veya eksik")
            return

        with self._lock:
            self._counts[kind] += 1
        try:
            boxes = self._frames if kind == "live" else self._meta
            await self._stream(connection, boxes, camera_id)
        finally:
            with self._lock:
                self._counts[kind] -= 1

    async def _stream(self, connection, boxes: dict[str, _Box], camera_id: str) -> None:
        last_seq = -1
        try:
            while True:
                box = boxes.get(camera_id)
                if box is not None and box.data is not None and box.seq != last_seq:
                    last_seq = box.seq
                    await connection.send(box.data)
                await asyncio.sleep(POLL_SEC)
        except ConnectionClosed:
            return
