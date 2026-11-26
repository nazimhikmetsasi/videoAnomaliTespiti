"""WRONG_DIRECTION kurali: yon bolgesinde izin verilen yonun tersine yuruyus.

Yer degistirme ve bolge vektoru PIKSEL uzayinda karsilastirilir: normalize
uzayda 16:9 sikismasi acilari bozar (docs/ASAMA13_5_PLAN.md SS2).
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

from vision.rules.engine import Candidate, Thresholds, Zone
from vision.stages.features import TrackWindow
from vision.stages.preprocess import FRAME_H, FRAME_W

DIR_SEC = 1.0             # bir adim dongusu (sag+sol) ~1 sn; net yer degistirme adim salinimini goturur
MIN_AGAINST_SPEED = 0.25  # boy/sn; yavas yuruyenin (~0.4) altinda, yerinde titreyeni eler
MAX_ANGLE_DEG = 60.0      # yol egriligi ve caprazlama yuruyuse pay; dik gecis ters yon sayilmaz

_MAX_COS = -math.cos(math.radians(MAX_ANGLE_DEG))


class DirectionRule:
    def __init__(self, zones: Sequence[Zone], clock: Callable[[], float]) -> None:
        self.zones = list(zones)
        self.clock = clock      # saat araligi duvar saatine bakar (bkz. zone.py)

    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        last = window.last
        zone = self._zone_for(last.foot)
        if zone is None:
            return None
        win = window.covering(DIR_SEC)
        if win is None:
            return None

        scale = np.array([FRAME_W, FRAME_H], dtype=float)
        d = (np.asarray(last.foot, dtype=float) - np.asarray(win[0].foot, dtype=float)) * scale
        v = np.asarray(zone.direction_vector, dtype=float) * scale
        u = v / np.linalg.norm(v)
        dt = last.ts - win[0].ts
        h = float(np.median([f.height for f in win]))
        dist = float(np.linalg.norm(d))
        if dt <= 0 or h <= 0 or dist <= 0:
            return None

        along = float(d @ u)
        against = -along / dt / h
        cos = along / dist
        if against < MIN_AGAINST_SPEED or cos > _MAX_COS:
            return None
        return Candidate(
            anomaly_type="WRONG_DIRECTION",
            track_ids=[window.track_id],
            score=min(-cos, 1.0),
            idx=last.idx,
            ts=last.ts,
            metrics={"against_speed": against, "cos": cos,
                     "dx_px": float(d[0]), "dy_px": float(d[1])},
            thresholds_used={"min_against_speed": MIN_AGAINST_SPEED,
                             "max_angle_deg": MAX_ANGLE_DEG},
            zone_name=zone.name,
        )

    def _zone_for(self, foot: np.ndarray) -> Zone | None:
        for zone in self.zones:
            vec = zone.direction_vector
            if zone.zone_type != "direction" or vec is None:
                continue
            if math.hypot(vec[0] * FRAME_W, vec[1] * FRAME_H) <= 0:
                continue
            if zone.active_at(self.clock()) and zone.contains(foot):
                return zone
        return None
