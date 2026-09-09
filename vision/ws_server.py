"""Canli goru WebSocket sunucusu: /ws/live/{camera_id} ikili JPEG,
/ws/meta/{camera_id} JSON (ASAMA6_PLAN.md SS3).

Kendi asyncio dongusunu ayri bir daemon thread'de calistirir -- ana goru
dongusu asla bloklanmaz. `publish_frame`/`publish_meta` kamera basina TEK
elemanli "son deger kazanir" bir kutuya yazar. Kuyruk yok: yavas istemci kare
biriktirmez, `vision/source.py`'nin canli kaynak kuralinin (en yeni kare
kazanir) ayni tasarimi.

Uyandirma OLAY GUDUMLUDUR, yoklama DEGIL. Onceki surum kutuyu 5 ms'de bir
yokluyordu ve bu olculmus bir hataydi: iki bagli istemcide saniyede 400
zamanlayici uyanmasi, CPU'su dolu goru dongusuyle GIL icin yarisiyordu.
Sonuc terstenti -- daha sik yoklama DAHA AZ kare teslim ediyordu, cunku
asyncio dongusu kit GIL zamanini gonderim yerine zamanlayici muhasebesine
harciyordu. Olculen degerler (zone_01, tek istemci):

    yoklama  5 ms : goru 18.6 FPS, istemci  1.0 FPS
    yoklama 33 ms : goru 26.6 FPS, istemci 21.6 FPS
    olay gudumlu  : asagidaki tasarim -- uyanma yalnizca yeni kare basina

Uretici her yayinda `loop.call_soon_threadsafe` ile bekleyen istemcilerin
`asyncio.Event`'lerini kurar; kare basina bir uyanma olur, bos gecen tek bir
uyanma kalmaz. Her baglanti KENDI Event'ini tasir -- paylasilan tek Event'te
"kim temizleyecek" yarisi olurdu.

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


class _Box:
    """Kamera basina "son deger kazanir" kutusu. `seq` degisince yeni veri var demektir.

    `data` kare icin `bytes` (BINARY WS cercevesi), meta icin `str` (TEXT WS
    cercevesi) tasir. `websockets` tip'e gore cerceveyi kendisi secer --
    meta'yi bytes olarak gondermek tarayicida `event.data` Blob/ArrayBuffer
    yapar, `JSON.parse` once `.text()` ister; `str` dogrudan calisir.

    `waiters` bu kutuyu bekleyen baglantilarin Event'leridir; uretici yayin
    yapinca hepsi kurulur."""

    __slots__ = ("data", "seq", "waiters")

    def __init__(self) -> None:
        self.data: bytes | str | None = None
        self.seq = 0
        self.waiters: set[asyncio.Event] = set()


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
        self._publish(self._frames, camera_id, jpeg)

    def publish_meta(self, camera_id: str, meta: dict) -> None:
        body = json.dumps(meta)   # str -> TEXT WS cercevesi (bkz. _Box docstring)
        self._publish(self._meta, camera_id, body)

    def _publish(self, boxes: dict[str, _Box], camera_id: str, payload: bytes | str) -> None:
        """Goru dongusunden cagrilir. Kilit yalnizca sozluk/kutu yazimi kadar
        tutulur; uyandirma kilidin DISINDA, call_soon_threadsafe ile asyncio
        thread'ine devredilir -- bu cagri geri donene kadar goru dongusu
        beklemez."""
        with self._lock:
            box = boxes.setdefault(camera_id, _Box())
            box.data = payload
            box.seq += 1
            waiters = list(box.waiters)
        if not waiters or self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(_wake_all, waiters)
        except RuntimeError:
            pass   # dongu kapaniyor; yayin kaybi kabul edilir, dongu duraklamaz

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
        event = asyncio.Event()
        with self._lock:
            box = boxes.setdefault(camera_id, _Box())
            box.waiters.add(event)
        last_seq = -1
        try:
            while True:
                # clear() OKUMADAN once gelir: aksi halde okuma ile clear
                # arasinda gelen bir yayin silinir ve o uyandirma kaybolurdu.
                event.clear()
                with self._lock:
                    data, seq = box.data, box.seq
                if data is not None and seq != last_seq:
                    last_seq = seq
                    await connection.send(data)
                    continue   # gonderirken yeni kare gelmis olabilir, hemen bak
                await event.wait()
        except ConnectionClosed:
            return
        finally:
            with self._lock:
                box.waiters.discard(event)


def _wake_all(waiters: list[asyncio.Event]) -> None:
    """asyncio thread'inde calisir (call_soon_threadsafe ile gonderilir)."""
    for event in waiters:
        event.set()
