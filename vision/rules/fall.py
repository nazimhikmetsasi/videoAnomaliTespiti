"""FALL kurali: hizli inis + ardindan yatay kalis (PLAN.md #4).

Tek basina yatay omurga (one egilen kisi) veya tek basina yuksek asagi hiz
(comelme) yeterli degil; dusme = hizli inis + sonrasinda yatay govde.
"""

from __future__ import annotations

from vision.rules.engine import Candidate, Thresholds
from vision.stages.features import TrackWindow

HOLD = 3            # body_tilt esiginin hepsini gecmesi gereken kare sayisi
VY_LOOKBACK = 15     # norm_vy tepe degerinin arandigi kare sayisi


class FallRule:
    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        held = window.recent(HOLD)
        if len(held) < HOLD or not all(f.body_tilt >= th.fall_tilt_deg for f in held):
            return None

        vy_window = [f.norm_vy for f in window.recent(VY_LOOKBACK)]
        vy_max = max(vy_window, default=0.0)
        if vy_max < th.fall_norm_vy:
            return None

        last = window.last
        score = 0.5 * min(last.body_tilt / th.fall_tilt_deg, 2.0) \
            + 0.5 * min(vy_max / th.fall_norm_vy, 2.0)
        return Candidate(
            anomaly_type="FALL",
            track_ids=[window.track_id],
            score=max(0.0, min(score, 1.0)),
            idx=last.idx,
            ts=last.ts,
            metrics={"body_tilt": last.body_tilt, "norm_vy_max": vy_max, "aspect": last.aspect},
            thresholds_used={"fall_tilt_deg": th.fall_tilt_deg, "fall_norm_vy": th.fall_norm_vy},
        )
