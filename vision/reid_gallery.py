"""Asama 11: olay tetiklemeli ReID galerisi — tekrar giren kisiyi baglar.

Takip kimligi (`track_id`) oturum icidir: kisi kadrajdan cikip geri girince
yeni bir ID alir (docs/DURUM.md, Asama 2'den beri acik soru). Bu sinif
olaylar arasinda kalici bir `person_id` uretir.

ReID agi HER KAREDE degil, yalnizca bir aday olay tetiklendiginde calisir.
Olculen bedel: takipte her karede ReID, 4 kamerada kamera basina 11.7 FPS;
kapaliyken 15.2 (Asama 10.4). Olay tetiklemeli akista maliyet kare basina
degil OLAY basina odenir.

Qdrant gibi ayri bir vektor veritabani kullanilmaz: galeri birkac yuz
vektordur, NumPy tek matris carpimiyla kosinus aramasi yapar. Ayri servis
dort konteynerin ustune besincisini koyar ve olculen sonucu degistirmez.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from vision.stages.tracker import DEFAULT_REID

DEFAULT_THRESHOLD = 0.75     # kosinus; Asama 11.3'te taranip secilecek
MAX_PEOPLE = 200             # galeri ust siniri
TTL_SEC = 3600.0             # bu kadar gorulmeyen kimlik dusurulur
MIN_CROP = 16                # bundan kucuk kirpim kodlayiciya verilmez


def sharpness(crop: np.ndarray) -> float:
    """Laplacian varyansi — buyuk olan daha keskin.

    Olay aninda kisinin goruntusu bulanik olabilir; en iyi kare secimi
    tekrar giris eslestirmesinin dogrulugunu artirir (oneri belgesi
    "Best-Frame Selection"). Maliyet yalnizca olay aninda odenir.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def crop_bbox(image: np.ndarray, bbox) -> np.ndarray | None:
    """Kare disina tasan kutuyu kirpar; cok kucuk kalirsa None."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < MIN_CROP or y2 - y1 < MIN_CROP:
        return None
    return image[y1:y2, x1:x2]


@dataclass
class Person:
    person_id: int
    vector: np.ndarray          # L2-normalize ortalama gomme
    count: int = 1
    last_seen: float = field(default_factory=time.time)


class ReIDGallery:
    """Gomme uretir, kosinusle eslestirir, kalici `person_id` dondurur."""

    def __init__(self, *, model: str = DEFAULT_REID, device: str = "cuda",
                 threshold: float = DEFAULT_THRESHOLD,
                 max_people: int = MAX_PEOPLE, ttl_sec: float = TTL_SEC) -> None:
        from ultralytics.trackers.bot_sort import build_encoder

        # ONNX Runtime cihaz INDEKSI ister; ciplak "cuda" sessizce CPU'ya
        # duser (kare basina ~30 ms). Ayni tuzak vision/stages/tracker.py'de
        # de yasandi, cozum orada da budur.
        self.device = "cuda:0" if device == "cuda" else device
        self.encoder = build_encoder(True, model, self.device)
        self.threshold = threshold
        self.max_people = max_people
        self.ttl_sec = ttl_sec
        self.people: list[Person] = []
        self._next_id = 1
        self.calls = 0              # kac kez kodlayici calisti (olay basina)
        self.encode_ms: list[float] = []
        self.matched = 0            # var olan kimlikle eslesen olay sayisi

    # ------------------------------------------------------------------ gomme
    def embed(self, image: np.ndarray, bboxes) -> np.ndarray | None:
        """(N, 4) kutu -> (N, 512) L2-normalize gomme. Kirpim gecersizse None."""
        boxes = np.asarray(bboxes, dtype=np.float32).reshape(-1, 4)
        if not len(boxes) or crop_bbox(image, boxes[0]) is None:
            return None
        # Kodlayici xyxy + conf + cls bekliyor (ultralytics sozlesmesi).
        dets = np.hstack([boxes, np.ones((len(boxes), 1), np.float32),
                          np.zeros((len(boxes), 1), np.float32)])
        t0 = time.perf_counter()
        out = self.encoder(image, dets)
        self.encode_ms.append((time.perf_counter() - t0) * 1000)
        self.calls += 1
        vectors = np.asarray([v for v in out if v is not None], dtype=np.float32)
        if not len(vectors):
            return None
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-9)

    # ------------------------------------------------------------- eslestirme
    def match(self, vector: np.ndarray, now: float | None = None) -> tuple[int, float]:
        """(person_id, en iyi kosinus). Esik altindaysa YENI kimlik acilir."""
        now = time.time() if now is None else now
        self._prune(now)
        if self.people:
            # Vektorler L2-normalize, dolayisiyla kosinus = ic carpim.
            bank = np.stack([p.vector for p in self.people])
            scores = bank @ vector
            best = int(np.argmax(scores))
            if float(scores[best]) >= self.threshold:
                self._merge(self.people[best], vector, now)
                self.matched += 1
                return self.people[best].person_id, float(scores[best])
            best_score = float(scores[best])
        else:
            best_score = 0.0
        person = Person(person_id=self._next_id, vector=vector, last_seen=now)
        self._next_id += 1
        self.people.append(person)
        self._cap()          # sinir EKLEDIKTEN sonra uygulanir, yoksa bir cagri gec kalir
        return person.person_id, best_score

    def identify(self, image: np.ndarray, bbox, now: float | None = None
                 ) -> tuple[int, float] | None:
        """Kirpim -> gomme -> eslestirme. Kirpim gecersizse None."""
        vectors = self.embed(image, [bbox])
        if vectors is None:
            return None
        return self.match(vectors[0], now)

    # -------------------------------------------------------------- ic isler
    def _merge(self, person: Person, vector: np.ndarray, now: float) -> None:
        """Kayan ortalama: tek kotu kirpim kimligi kacirmasin."""
        blended = person.vector * person.count + vector
        person.vector = blended / max(float(np.linalg.norm(blended)), 1e-9)
        person.count += 1
        person.last_seen = now

    def _prune(self, now: float) -> None:
        self.people = [p for p in self.people if now - p.last_seen <= self.ttl_sec]

    def _cap(self) -> None:
        """En eski gorulenler duser; galeri sinirsiz buyumez."""
        if len(self.people) > self.max_people:
            self.people.sort(key=lambda p: p.last_seen, reverse=True)
            del self.people[self.max_people:]
