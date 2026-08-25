"""ZONE_VIOLATION kurali: yasak/kisitli-saat bolgesine giris (PLAN.md #4).

Ayak noktasi kullanilir, bbox merkezi degil: kisi bolge kenarinda dururken
govdesi iceri sarkabilir; ihlali belirleyen ayagin nerede durdugudur.
"""

from __future__ import annotations

from typing import Sequence

from vision.rules.engine import Candidate, Thresholds, Zone
from vision.stages.features import TrackWindow

HOLD = 3            # ayagin bolge icinde kalmasi gereken kare sayisi
SCORE_LOOKBACK = 5


class ZoneRule:
    def __init__(self, zones: Sequence[Zone]) -> None:
        self.zones = list(zones)

    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        last = window.last
        for zone in self.zones:
            if zone.zone_type not in ("forbidden", "restricted_hours"):
                continue
            if zone.zone_type == "restricted_hours" and not zone.active_at(last.ts):
                continue
            if not zone.contains(last.foot):
                continue

            held = window.recent(HOLD)
            if len(held) < HOLD or not all(zone.contains(f.foot) for f in held):
                continue

            scored = window.recent(SCORE_LOOKBACK)
            score = sum(1 for f in scored if zone.contains(f.foot)) / len(scored)
            return Candidate(
                anomaly_type="ZONE_VIOLATION",
                track_ids=[window.track_id],
                score=score,
                idx=last.idx,
                ts=last.ts,
                metrics={"foot_x": float(last.foot[0]), "foot_y": float(last.foot[1])},
                thresholds_used={},
                zone_name=zone.name,
            )
        return None
