"""LOITERING kurali: bolgede uzun kalis veya sabit dolanma (PLAN.md #4).

Pencere (window_frames=30, ~1.2 sn @25 FPS) loiter_sec (varsayilan 30 sn)
tutamaz; bu yuzden kural kendi girisini (enter_ts) ve cipasini (anchor)
kendi durumunda saklar. Iz kaybolunca (STALE_FRAMES) durum duser. Ayni iz
tetikledikten sonra RETRIGGER_SEC boyunca susar; yoksa 30 sn'lik bekleyis
her karede yeni aday uretir.

Iki mod, bolge tanimli olup olmamasina gore SABIT secilir (kare kare
degil): bolge varsa ayagin bolgede kesintisiz kalisi, yoksa merkezin
kendi yuksekliginden fazla kaymamasi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from vision.rules.engine import Candidate, Thresholds, Zone
from vision.stages.features import FrameFeatures, TrackWindow

STALE_FRAMES = 90
RETRIGGER_SEC = 10.0


@dataclass
class _State:
    enter_ts: float
    anchor: np.ndarray
    last_seen_idx: int
    last_trigger_ts: float | None = None


class LoiterRule:
    def __init__(self, zones: Sequence[Zone] = ()) -> None:
        self.zones = list(zones)
        self._state: dict[int, _State] = {}

    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        last = window.last
        self._prune(last.idx)

        st = self._state.get(window.track_id)
        if self.zones:
            zone = self._matching_zone(last)
            still = zone is not None
        else:
            zone = None
            still = st is not None and self._drift(last, st.anchor) <= last.height

        if st is None or not still:
            self._state[window.track_id] = _State(last.ts, last.centroid, last.idx)
            return None

        st.last_seen_idx = last.idx
        dwell = last.ts - st.enter_ts
        if dwell < th.loiter_sec:
            return None
        if st.last_trigger_ts is not None and last.ts - st.last_trigger_ts < RETRIGGER_SEC:
            return None

        st.last_trigger_ts = last.ts
        return Candidate(
            anomaly_type="LOITERING",
            track_ids=[window.track_id],
            score=min(dwell / th.loiter_sec, 1.0),
            idx=last.idx,
            ts=last.ts,
            metrics={"dwell_sec": dwell, "drift": self._drift(last, st.anchor)},
            thresholds_used={"loiter_sec": float(th.loiter_sec)},
            zone_name=zone.name if zone is not None else None,
        )

    def _matching_zone(self, feat: FrameFeatures) -> Zone | None:
        for zone in self.zones:
            if zone.zone_type not in ("forbidden", "restricted_hours"):
                continue
            if zone.zone_type == "restricted_hours" and not zone.active_at(feat.ts):
                continue
            if zone.contains(feat.foot):
                return zone
        return None

    @staticmethod
    def _drift(feat: FrameFeatures, anchor: np.ndarray) -> float:
        return float(np.linalg.norm(feat.centroid - anchor))

    def _prune(self, idx: int) -> None:
        stale = [tid for tid, st in self._state.items() if idx - st.last_seen_idx > STALE_FRAMES]
        for tid in stale:
            del self._state[tid]
