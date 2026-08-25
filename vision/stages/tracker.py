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

# Paketle gelen varsayilanlarin uzerine yazilanlar.
OVERRIDES = {
    "with_reid": True,       # `model: auto` ile bedava: dedektorun kendi oznitelikleri
    "model": "auto",
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
        self.cfg.device = device
        self._tracker = BOTSORT(self.cfg)
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
