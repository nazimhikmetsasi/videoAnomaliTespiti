"""Video kaynagi: mp4 dosyasi, webcam ve RTSP icin tek arayuz.

Tasarim kararlari:

- Yakalama ayri bir is parcaciginda doner. Cikarim dongusu disk/ag I/O'su
  icin beklemez; GPU bosta kalmaz.
- Halka tampon son N kareyi tutar. Asama 6'daki +-5 sn kanit klibi buradan
  uretilir, kare yeniden okunmaz.
- Canli kaynakta (webcam/RTSP) tuketici yavas kalirsa en eski kare atilir;
  gecikme birikmez. Dosya kaynaginda atilmaz, uretici bekler — kayitli
  videodan tek kare bile kaybolmamalidir (degerlendirme tekrar edilebilir
  olmali).
- RTSP kopmasi kacinilmazdir (PLAN.md risk 5). Ustel geri cekilmeli yeniden
  baglanma bastan zorunlu, sonraya birakilmaz.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

import dataclasses

import cv2
import numpy as np

BUFFER_FRAMES = 300          # 25 FPS'te 12 sn — +-5 sn klip icin fazlasiyla yeter
# Halka tampon kare SAYISIYLA sinirli; bayt ile degil. 4K kaynakta kare
# basina 24.9 MB demek: tek kamera icin 7.5 GB. Asama 10.5'in 1 saatlik
# kosusunda olculdu — RSS 0.9-4.9 GB arasi salindi ve 13. dakikada surec
# "cuDNN error: CUDNN_STATUS_EXECUTION_FAILED" ile oldu (GPU bellegi
# sabit 1131 MB'taydi, yani VRAM tasmasi DEGIL; host bellegi tukenmisti).
# Cozum: tamponda saklanan kopya bu genislige kucultulur. Kuyruga giden
# kare HAM kalir, yani tespit kalitesi degismez; yalnizca kanit klibinin
# cozunurlugu sinirlanir -- panel zaten 960x540 gosteriyor.
BUFFER_MAX_W = 960
RECONNECT_START_SEC = 0.5
RECONNECT_MAX_SEC = 30.0


@dataclass
class Frame:
    """Tek kare ve kimligi. `idx` kaynak acilisindan beri artan sayacdir."""

    idx: int
    ts: float
    image: np.ndarray


def classify_source(source: str | int) -> str:
    """Kaynagi webcam / rtsp / file olarak siniflandirir."""
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        return "webcam"
    if str(source).lower().startswith(("rtsp://", "rtmp://", "http://", "https://")):
        return "rtsp"
    return "file"


class VideoSource:
    """Arka planda kare okuyan kaynak.

    Kullanim:
        with VideoSource("data/test.mp4") as src:
            while (frame := src.read()) is not None:
                ...
    """

    def __init__(
        self,
        source: str | int,
        *,
        buffer_frames: int = BUFFER_FRAMES,
        reconnect_max_sec: float = RECONNECT_MAX_SEC,
        loop: bool = False,
    ) -> None:
        self.source = source
        self.source_type = classify_source(source)
        self.is_live = self.source_type != "file"
        self.reconnect_max_sec = reconnect_max_sec
        # Canli kaynakta anlami yok (akis zaten hic bitmez) -- sessizce yok
        # sayilir, cagiran taraf her kaynak turu icin ayri kontrol yazmasin.
        self.loop = loop and not self.is_live
        # Ozniteliklerin zaman kaynagi budur (PLAN.md Asama 3): klip 25 FPS
        # kayitken hat 37 FPS calisirsa duvar saati hizlari 1.5 kat sisirir.
        # Canlida gercek FPS onemsiz, duvar saati (frame.ts) kullanilacak.
        self.fps = 25.0
        if not self.is_live:
            probe = cv2.VideoCapture(str(source))
            fps = probe.get(cv2.CAP_PROP_FPS) if probe.isOpened() else 0.0
            probe.release()
            if fps and fps > 0:
                self.fps = float(fps)

        # Kanit tamponu: hicbir zaman tuketilmez, sadece en eskisi dusurulur.
        self._buffer: deque[Frame] = deque(maxlen=buffer_frames)
        self._buffer_lock = threading.Lock()

        # Devir teslim: canlida tek yuva (en yenisi kazanir), dosyada kuyruk
        # dolunca uretici bekler.
        self._queue: queue.Queue[Frame] = queue.Queue(maxsize=1 if self.is_live else 64)

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.eof = threading.Event()

        self.frames_read = 0
        self.frames_dropped = 0
        self.reconnects = 0
        self.last_error: str | None = None

    # --- yasam dongusu ---------------------------------------------------

    def start(self) -> "VideoSource":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._run, name="capture", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def __enter__(self) -> "VideoSource":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # --- tuketici tarafi -------------------------------------------------

    def read(self, timeout: float = 2.0) -> Frame | None:
        """Siradaki kareyi verir. Kaynak bittiyse veya sure dolduysa None.

        Bekleme SURESI `timeout`u asmaz. Once sabit 0.1 sn'lik parcalarla
        beklenirdi; coklu kamerada (Asama 10.3) bu, kare hazir olmayan
        webcam'in TUM turu 0.1 sn bloklamasi demekti ve dosya kameralari
        11.4'ten 7.1 FPS'e dusuyordu. timeout=0 artik gercekten bloklamaz.
        """
        deadline = time.monotonic() + timeout
        while True:
            wait = min(0.1, deadline - time.monotonic())
            try:
                if wait > 0:
                    return self._queue.get(timeout=wait)
                return self._queue.get_nowait()
            except queue.Empty:
                if self.eof.is_set() or self._stop.is_set():
                    return None
                if time.monotonic() >= deadline:
                    return None

    def _buffer_copy(self, frame: Frame) -> Frame:
        """Tampona giden kopya: genisligi BUFFER_MAX_W'yi asmaz."""
        if frame.image is None:
            return frame
        height, width = frame.image.shape[:2]
        if width <= BUFFER_MAX_W:
            return frame
        scale = BUFFER_MAX_W / width
        small = cv2.resize(frame.image, (BUFFER_MAX_W, max(1, round(height * scale))),
                           interpolation=cv2.INTER_AREA)
        return dataclasses.replace(frame, image=small)

    def snapshot(self) -> list[Frame]:
        """Tampondaki kareleri kopyalar (kanit klibi icin)."""
        with self._buffer_lock:
            return list(self._buffer)

    # --- uretici tarafi --------------------------------------------------

    def _open(self) -> cv2.VideoCapture | None:
        target = int(self.source) if self.source_type == "webcam" else str(self.source)
        cap = cv2.VideoCapture(target)
        if not cap.isOpened():
            cap.release()
            return None
        if self.is_live:
            # Surucu tarafinda kare birikmesin; gecikme yerine tazelik istiyoruz.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _publish(self, frame: Frame) -> None:
        with self._buffer_lock:
            self._buffer.append(self._buffer_copy(frame))

        if self.is_live:
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self.frames_dropped += 1
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(frame)
                except queue.Full:
                    self.frames_dropped += 1
            return

        # Dosya: kare atmak yok, tuketici hizina uy.
        while not self._stop.is_set():
            try:
                self._queue.put(frame, timeout=0.2)
                return
            except queue.Full:
                continue

    def _run(self) -> None:
        cap: cv2.VideoCapture | None = None
        backoff = RECONNECT_START_SEC
        idx = 0

        while not self._stop.is_set():
            if cap is None:
                cap = self._open()
                if cap is None:
                    self.last_error = f"kaynak acilamadi: {self.source}"
                    if not self.is_live:
                        self.eof.set()
                        return
                    self.reconnects += 1
                    if self._stop.wait(backoff):
                        return
                    backoff = min(backoff * 2, self.reconnect_max_sec)
                    continue
                backoff = RECONNECT_START_SEC

            ok, image = cap.read()
            if not ok:
                if self.loop:
                    # Basa sar -- idx SIFIRLANMAZ, surekli artan sayac olarak
                    # kalir. Boylece Smoother/FeatureEngine/RuleEngine'in iz
                    # kimlikleri ve kural pencereleri (Asama 3) sarim aninda
                    # bozulmaz; ts = idx/fps (vision/run.py) hep ileri gider.
                    # Pilot klipler 8-60 sn -- demo boyunca kamera "olmemeli".
                    # Daha onemlisi: dosya kaynagi _EOS ile bittiginde Spark
                    # oturumu OLAYIN degil AKISIN bitisiyle kapaniyordu ve
                    # Asama 6'da olculen 13.9-54.8 sn "alarm gecikmesi" bu
                    # yuzden hattin hizini DEGIL akisin bitisini olcuyordu
                    # (docs/DURUM.md acik sorusu). Dongude akis hic bitmez,
                    # olcum anlamli hale gelir.
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                cap.release()
                cap = None
                if not self.is_live:
                    self.eof.set()   # dosya bitti, normal son
                    return
                self.last_error = "akis koptu, yeniden baglaniliyor"
                self.reconnects += 1
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, self.reconnect_max_sec)
                continue

            self.frames_read += 1
            self._publish(Frame(idx=idx, ts=time.time(), image=image))
            idx += 1

        if cap is not None:
            cap.release()
