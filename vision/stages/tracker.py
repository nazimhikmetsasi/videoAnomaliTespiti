"""BoT-SORT sarmalayici: kalici track_id + gorunum (ReID) + kamera hareketi
telafisi (GMC).

v1 DeepSORT + mobilenet gomucusu kullaniyor ve zayif ReID'i elle yamalarla
(~250 satir: `_is_sane_bbox`, `_merge_overlaps`, `_soft_reacquire`) telafi
etmeye calisiyordu (PLAN.md zayif nokta 2 ve 3). BoT-SORT bunlari hazir
getirir; yamalar hic dogmaz.

Neden `model.track()` degil de dogrudan BOTSORT: ultralytics'in track yolu
toplu cikarimda tum kareler icin TEK tracker kullanir. Coklu kamerada
(Asama 10) her kameranin kendi tracker'i olmak zorundadir. Kamera basina bir
`Tracker` ornegi bunu dogal olarak saglar.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml

# YOLO26 end2end oldugu icin dedektorun bedava govde oznitelikleri ReID'e
# baglanamaz (ultralytics `trackers/track.py` bunu acikca disliyor). Amaca
# ozel egitilmis ReID agi bunun yerine gecer: crop -> 224x224 -> gomme vektoru.
DEFAULT_REID = "models/yolo26s-reid.onnx"

# ONNX Runtime CUDA saglayicisi girdi sekli her degistiginde yeniden ayarlama
# yapiyor. Olculen bedel ~50 ms ve ISITMA BUNU ONLEMIYOR: daha once gorulmus
# bir sekle donuldugunde de yeniden odeniyor. Kisi sayisi kareden kareye
# oynadigi icin bu, 40 ms'lik 25 FPS butcesini tek basina asan duzenli
# sicramalar demekti (police_run: medyan 0.5 ms, p95 50.4 ms). Batch bu sayinin
# katina yuvarlanir, sekil sabit kalir.
#
# Adim 2 olculerek secildi (police_run, ayni kosullar):
#   yuvarlama yok : takip medyan  0.5 ms, p95 50.4 ms
#   adim 4        : takip medyan 10.1 ms, p95 18.9 ms
#   adim 2        : takip medyan  7.1 ms, p95 13.4 ms   <- secilen
# Sabit maliyet batch ile buyudugu icin kucuk adim daha ucuz; 3+ kisilik
# karelerde 4'e cikilir ve sekil yine sabit kalir.
REID_BATCH_STEP = 2

# Paketle gelen varsayilanlarin uzerine yazilanlar.
OVERRIDES = {
    "with_reid": True,
    "model": "auto",         # end2end olmayan dedektorde bedava oznitelik yolu
    "track_high_thresh": 0.30,
    "new_track_thresh": 0.35,
    "track_buffer": 60,      # 25 FPS'te ~2.4 sn: kisa kapanmalarda ID korunur
    # GMC (kamera hareketi telafisi) varsayilan olarak KAPALI. Alti pilot
    # klipte acik/kapali ID sonuclari birebir ayni cikti, buna karsilik
    # sparseOptFlow kare basina ~18 ms yiyip FPS'i yariya dusurdu. Sabit
    # gozetim kamerasinda telafi edecek hareket yok. PTZ veya elde tasinan
    # kamerada `gmc_method="sparseOptFlow"` ile acilir.
    "gmc_method": "none",
}


class _FixedBatchReID:
    """ReID cagrilarini sabit batch boyutuna yuvarlayan sarmalayici.

    Eksik yerler son tespitin kopyasiyla doldurulur, fazla gomme vektorleri
    atilir. Bedeli az sayida gereksiz kirpim; kazanci sekil degisimi kaynakli
    ~50 ms'lik sicramalarin tamamen kalkmasi.
    """

    def __init__(self, inner, step: int = REID_BATCH_STEP) -> None:
        self.inner = inner
        self.step = step

    def __call__(self, img: np.ndarray, dets: np.ndarray):
        n = len(dets)
        if n == 0:
            return []
        pad = (-n) % self.step
        if pad:
            dets = np.vstack([dets, np.repeat(dets[-1:], pad, axis=0)])
        return self.inner(img, dets)[:n]


@dataclass
class Track:
    """Tek kisinin tek karedeki durumu. Asama 3 ozniteliklerinin girdisi."""

    track_id: int
    bbox: np.ndarray                 # xyxy, letterbox kare uzayinda
    conf: float
    keypoints: np.ndarray | None     # (17, 3) -> x, y, guven; pose yoksa None

    @property
    def height(self) -> float:
        """bbox yuksekligi — tum hiz/mesafe esiklerinin normalizasyon birimi."""
        return float(self.bbox[3] - self.bbox[1])


class Tracker:
    """Kamera basina bir ornek. `update` her kare cagrilir."""

    def __init__(self, *, device: str = "cuda", **overrides) -> None:
        cfg = YAML.load(check_yaml("botsort.yaml"))
        cfg.update(OVERRIDES)
        cfg.update(overrides)
        self.cfg = IterableSimpleNamespace(**cfg)
        # ONNX ReID agi cihaz indeksi ister; ciplak "cuda" torch.device icinde
        # index=None olur ve ONNX Runtime CUDA saglayicisini reddedip sessizce
        # CPU'ya duser (kare basina ~30 ms). Indeks acikca verilir.
        self.cfg.device = "cuda:0" if device == "cuda" else device
        self._tracker = BOTSORT(self.cfg)
        # `model: auto` yolunda encoder gomme degil hazir oznitelik alir ve
        # ONNX calismaz — yalnizca gercek ReID agi sarmalanir.
        if self.cfg.model != "auto" and self._tracker.encoder is not None:
            self._tracker.encoder = _FixedBatchReID(self._tracker.encoder)
        self.frames = 0
        self.seen_ids: set[int] = set()

    def reset(self) -> None:
        self._tracker.reset()
        self.frames = 0
        self.seen_ids.clear()

    def update(self, result, image: np.ndarray) -> list[Track]:
        """Bir karenin tespitlerini takibe verir, kalici ID'li izleri dondurur.

        Args:
            result: ultralytics Results (tek kare).
            image: tracker'a verilen kare — GMC bunu optik akis icin kullanir.
        """
        self.frames += 1
        boxes = result.boxes.cpu().numpy()
        feats = getattr(result, "feats", None)
        rows = self._tracker.update(boxes, image, feats=feats)
        if len(rows) == 0:
            return []

        keypoints = None
        if result.keypoints is not None and len(result.keypoints.data):
            keypoints = result.keypoints.data.cpu().numpy()

        tracks = []
        for row in rows:
            # row = [x1, y1, x2, y2, track_id, score, cls, det_idx]
            det_idx = int(row[7])
            track_id = int(row[4])
            self.seen_ids.add(track_id)
            kp = None
            if keypoints is not None and det_idx < len(keypoints):
                kp = keypoints[det_idx]
            tracks.append(
                Track(
                    track_id=track_id,
                    bbox=row[:4].astype(np.float32).copy(),
                    conf=float(row[5]),
                    keypoints=kp,
                )
            )
        return tracks
