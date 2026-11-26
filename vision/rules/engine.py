"""Kural motoru: FeatureEngine ciktisini aday anomali olaylarina cevirir.

Poz yoksa anomali uretilmez kurali (PLAN.md zayif nokta 7, altigi pilot
klipte pozsuz iz sayisi 0 olcumune ragmen yazilir) burada TEK noktada
uygulanir: pencerenin son karesi pozsuzsa hicbir kurala verilmez. Bu
kontrolu bes kural dosyasina ayri ayri kopyalamak PLAN.md'nin v1'den
kacindigi yama yigininin ta kendisidir.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from typing import Callable, Sequence

import cv2
import numpy as np

from vision.stages.features import TrackWindow


@dataclass
class Thresholds:
    """infra/postgres/init.sql detection_settings ile birebir."""

    pose_conf: float = 0.25
    track_conf: float = 0.30
    fall_tilt_deg: float = 45.0
    fall_norm_vy: float = 1.20
    run_norm_speed: float = 1.80    # SS10.5#2: NORMAL p90 (0.648) >= olay p10 (0.037), ortusuyor -- olculemedi, varsayilan korundu
    # Kayan medyan penceresi 50 kareye cikarilinca olculdu: NORMAL p95 1.00,
    # p99 1.44; gercek kosu (run_01) medyani 1.46 ve klip boyunca 1.45-1.66
    # bandinda kaliyor. 1.20 ikisinin arasindadir. 10 karelik pencerede ayrim
    # yoktu (NORMAL p95 1.28) -- yuruyusun tek adimlik sicramasi mediana
    # tasiyordu.
    run_gait_speed: float = 1.20
    loiter_sec: int = 30
    fight_proximity: float = 1.20
    # DB sutunu olarak kaliyor; vision tarafi artik okumuyor, pencereler saniye
    # cinsinden (docs/ASAMA13_3_PLAN.md SS9).
    window_frames: int = 50


@dataclass
class Zone:
    name: str
    zone_type: str                              # forbidden / restricted_hours / direction
    polygon: np.ndarray                         # (N, 2) 0-1 normalize
    active_from: datetime.time | None = None
    active_to: datetime.time | None = None
    direction_vector: tuple[float, float] | None = None

    def contains(self, point: np.ndarray) -> bool:
        pt = (float(point[0]), float(point[1]))
        return cv2.pointPolygonTest(self.polygon.astype(np.float32), pt, False) >= 0

    def active_at(self, ts: float) -> bool:
        """Saat araligi; None = hep aktif."""
        if self.active_from is None or self.active_to is None:
            return True
        now = datetime.datetime.fromtimestamp(ts).time()
        if self.active_from <= self.active_to:
            return self.active_from <= now <= self.active_to
        return now >= self.active_from or now <= self.active_to  # gece yarisini gecen aralik


@dataclass
class Candidate:
    anomaly_type: str            # FALL / RUN / ZONE_VIOLATION / LOITERING / FIGHT
    track_ids: list[int]
    score: float                 # 0-1
    idx: int
    ts: float
    metrics: dict[str, float]
    thresholds_used: dict[str, float]
    zone_name: str | None = None
    decided_by: str = "rule"     # rule / model / hybrid — Asama 9 ablation kaynagi
    event_time: float | None = None   # duvar saati (epoch sn); None = eski davranis


class RuleEngine:
    def __init__(self, thresholds: Thresholds = Thresholds(),
                 zones: Sequence[Zone] = (),
                 clock: Callable[[], float] = time.time) -> None:
        self.thresholds = thresholds
        self.zones = list(zones)
        self.clock = clock      # restricted_hours icin duvar saati

        # Kural siniflari burada, __init__ govdesinde import edilir --
        # modul basinda import edilirse engine.py <-> fall.py/run.py/... arasi
        # dongusel import olusur (kurallar Candidate/Thresholds/Zone icin
        # engine.py'a bakar). __init__ ilk cagrildiginda engine modulu zaten
        # tam yuklu oldugu icin dongu kirilir.
        from vision.rules.fall import FallRule
        from vision.rules.run import RunRule
        from vision.rules.direction import DirectionRule
        from vision.rules.zone import ZoneRule
        from vision.rules.loiter import LoiterRule
        from vision.rules.fight import FightRule

        self._fall = FallRule()
        self._run = RunRule()
        self._zone = ZoneRule(self.zones, self.clock)
        self._loiter = LoiterRule(self.zones, self.clock)
        self._direction = DirectionRule(self.zones, self.clock)
        self._fight = FightRule()

    def __call__(self, windows: dict[int, TrackWindow]) -> list[Candidate]:
        posed = {tid: w for tid, w in windows.items() if w.last.has_pose}

        candidates: list[Candidate] = []
        for rule in (self._fall, self._run, self._zone, self._loiter,
                     self._direction):
            for window in posed.values():
                cand = rule.check(window, self.thresholds)
                if cand is not None:
                    candidates.append(cand)
        candidates.extend(self._fight.check_all(posed, self.thresholds))
        return candidates

    def set_zones(self, zones: Sequence[Zone]) -> None:
        """Canli bolge degisimi (SettingsClient). Once yeni nesneler kurulur,
        sonra atanir: ana dongu yari guncellenmis kural gormez. Oyalanma
        sayaclari bolge tanimi degisince anlamini yitirdigi icin sifirlanir."""
        from vision.rules.direction import DirectionRule
        from vision.rules.loiter import LoiterRule
        from vision.rules.zone import ZoneRule

        zones = list(zones)
        zone_rule = ZoneRule(zones, self.clock)
        loiter = LoiterRule(zones, self.clock)
        direction = DirectionRule(zones, self.clock)
        self.zones = zones
        self._zone, self._loiter, self._direction = zone_rule, loiter, direction
