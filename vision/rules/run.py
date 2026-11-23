"""RUN kurali: surekliligi olan yuksek yatay hiz (PLAN.md #4).

Son 0.36 sn'deki karelerin en az %60'inda esik asilmali (25 FPS'te 10
karede 6) -- suzulme sarti tek karelik dedektor sicramasini eler.

SS10.3: norm_speed (goruntu yatay hizi) ozne kamera eksenine dogru/kameradan
uzaklasarak hareket ederse veya kamera ozneyi takip ederse gozlemlenemez
(olculen tepe: run_01 0.41, mixed_01 1.04, police_run 1.77 -- esik 1.80,
sabit kamerada bile kil payi altinda). limb_speed medyani (adim ritmi) kamera
geometrisinden bagimsizdir; ikinci, bagimsiz tetikleyici olarak eklendi.
"""

from __future__ import annotations

import math
import statistics

from vision.rules.engine import Candidate, Thresholds
from vision.stages.features import EPS, TrackWindow

SPEED_SEC = 0.36     # yer degistirme kaniti penceresi; 25 FPS'te 10 kare
MIN_HIT_RATIO = 0.6  # penceredeki karelerin esigi asmasi gereken orani; 25 FPS'te 6/10
# Adim kanitinin penceresi yer degistirme kanitininkinden UZUNDUR. Olculdu:
# 10 karelik (0.36 sn) medyanda yuruyusun tek adimlik sicramasi kosu bandina giriyor
# (NORMAL p95 1.28, gercek kosu 1.45 -- ayrisma yok), 50 karede yuruyus
# p95'i 1.00'a duserken kosu 1.46'da kaliyor. Bedeli: kosu 2 saniye once
# degil, 2 saniye sonra bildirilir.
GAIT_SEC = 1.96      # 25 FPS'te 50 kare


class RunRule:
    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        recent = window.covering(SPEED_SEC)
        if recent is None:
            return None

        speeds = [f.norm_speed for f in recent]
        gait_window = window.covering(GAIT_SEC)
        hits = sum(1 for s in speeds if s >= th.run_norm_speed)
        # Medyan, tepe degil: tek karelik keypoint sicramasi yuruyuste de
        # gait_median'i sisirebilir (olculen fall_01 5.34 sn: limb_speed 3.26).
        gait_median = (statistics.median(f.limb_speed for f in gait_window)
                       if gait_window is not None else 0.0)
        if hits < math.ceil(MIN_HIT_RATIO * len(recent) - EPS) and gait_median < th.run_gait_speed:
            return None

        median = statistics.median(speeds)
        last = window.last
        score = max(median / th.run_norm_speed, gait_median / th.run_gait_speed)
        return Candidate(
            anomaly_type="RUN",
            track_ids=[window.track_id],
            score=max(0.0, min(score, 1.0)),
            idx=last.idx,
            ts=last.ts,
            metrics={"norm_speed_median": median, "norm_speed_max": max(speeds),
                     "limb_speed_median": gait_median},
            thresholds_used={"run_norm_speed": th.run_norm_speed, "run_gait_speed": th.run_gait_speed},
        )
