"""FIGHT kurali: ikili yakinlik + yuksek uzuv hizi (PLAN.md #4).

PLAN.md risk 3: kural tabanli kavga tespiti yaklasik %70 dogruluktur;
gercek cozum Asama 9 TCN modelidir. Bu kural o zamana kadar taban
cizgisidir.
"""

from __future__ import annotations

import itertools

import numpy as np

from vision.rules.engine import Candidate, Thresholds
from vision.stages.features import TrackWindow


def pair_proximity(wi: TrackWindow, wj: TrackWindow) -> float:
    """Iki izin merkez mesafesi / ortalama bbox yuksekligi. Olcek-normalize."""
    fi, fj = wi.last, wj.last
    mean_h = (fi.height + fj.height) / 2
    if mean_h <= 0:
        return 1e9
    return float(np.linalg.norm(fi.centroid - fj.centroid) / mean_h)


def close_pairs(windows: dict[int, TrackWindow], th: Thresholds) -> set[int]:
    """Yakin bir cifte ait iz kimlikleri.

    HybridArbiter da bunu kullanir: model FIGHT dedi diye tek basina aday
    uretmek yanlistir (kavga ikili bir olaydir) ama YAKINLIK sartini
    kuralin uzuv hizi sartindan AYIRMAK gerekti. Olculdu (Asama 11):
    uzuv hizi FIGHT'i NORMAL'den ayirmiyor -- 0.5 ve ustu her esikte NORMAL
    orani daha yuksek. Yakinlik ise tutuyor (FIGHT kliplerinde medyan 0.93,
    esik 1.20). Bu yuzden yakinlik paylasilir, uzuv hizi kurala ozel kalir.
    """
    close: set[int] = set()
    for wi, wj in itertools.combinations(windows.values(), 2):
        if pair_proximity(wi, wj) < th.fight_proximity:
            close.add(wi.track_id)
            close.add(wj.track_id)
    return close

HOLD = 3                    # cift bazli sart surekliligi, kare sayisi
FIGHT_LIMB_SPEED = 2.0       # normalize uzuv hizi esigi (1/sn)


class FightRule:
    def __init__(self, limb_speed_th: float = FIGHT_LIMB_SPEED) -> None:
        self.limb_speed_th = limb_speed_th
        self._streak: dict[tuple[int, int], int] = {}

    def check_all(self, windows: dict[int, TrackWindow], th: Thresholds) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen: set[tuple[int, int]] = set()
        for wi, wj in itertools.combinations(windows.values(), 2):
            pair = (min(wi.track_id, wj.track_id), max(wi.track_id, wj.track_id))
            seen.add(pair)
            cand = self._check_pair(wi, wj, pair, th)
            if cand is not None:
                candidates.append(cand)

        # Bu karede birlikte gorulmeyen ciftlerin serisi anlamsiz -- dus.
        for pair in list(self._streak):
            if pair not in seen:
                del self._streak[pair]
        return candidates

    def _check_pair(self, wi: TrackWindow, wj: TrackWindow, pair: tuple[int, int],
                     th: Thresholds) -> Candidate | None:
        fi, fj = wi.last, wj.last
        proximity = pair_proximity(wi, wj)

        met = (proximity < th.fight_proximity
               and fi.limb_speed >= self.limb_speed_th
               and fj.limb_speed >= self.limb_speed_th)
        if not met:
            self._streak[pair] = 0
            return None

        self._streak[pair] = self._streak.get(pair, 0) + 1
        if self._streak[pair] < HOLD:
            return None

        limb_min = min(fi.limb_speed, fj.limb_speed)
        return Candidate(
            anomaly_type="FIGHT",
            track_ids=list(pair),
            score=max(0.0, min(limb_min / self.limb_speed_th, 1.0)),
            idx=fi.idx,
            ts=fi.ts,
            metrics={"proximity": proximity, "limb_speed_min": limb_min},
            thresholds_used={"fight_proximity": th.fight_proximity, "fight_limb_speed": self.limb_speed_th},
        )
