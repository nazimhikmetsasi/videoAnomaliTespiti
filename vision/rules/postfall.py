"""Dusme sonrasi izleme: kisi kalkabildi mi (docs/ASAMA13_4_PLAN.md).

FALL kurali anlik bir darbeyi yakalar; sonrasina bakmaz. Burada dusen kisi
DECIDE_SEC boyunca izlenir ve olaya bir sonuc eklenir: down / recovered /
unknown. Izleme olay yolunun DISINDA calisir, FALL alarmini geciktirmez.

Karar harekete degil DURUSA bakar: kalkmayi deneyip basaramayanlar daha cok
hareket eder, hareket sarti tam da yerde cabalayan kisiyi kacirirdi. Hareket
yalniz raporlanir (limb_speed_med).

Dusen iz kaybolursa ayni yerde ilk kez gorulen yeni iz devralinir: yerde
yatan kisi yeniden algilaninca izleyici ona yeni kimlik veriyor. Devralma
yalniz dusen iz o karede gorunmuyorken ve yeni iz dusme yerinde dogduysa
olur; kapidan gelen yardimci devralinmaz.

Hata iki yone esit degil, guvenli taraf alarm: son gorulen durus yatay ise
kisi uzun suredir gorunmese de "down"; oturan veya yarim kalkan "unknown"
(olay bugunku gibi kritik kalir); "recovered" icin kesintisiz ayakta durmak
gerekir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from vision.rules.engine import Candidate, Thresholds
from vision.stages.features import EPS, STALE_SEC, TrackWindow

DECIDE_SEC = 25.0   # Schwickert 2018: >24.5 sn dinlenme kalkamamayi ongorur (AUC 0.796)
UPRIGHT_SEC = 2.0   # kaynaksiz: sistemin davranis gozlem penceresi (TCN 1.96, RETAIN_SEC 2.0)
STAND_RATIO = 0.88  # Winter 2009 oranlari: sandalyede oturan ~0.76, ayakta 1.0; ikisinin ortasi
ADOPT_DIST = 1.0    # LoiterRule "yerinde" olcusu: merkez kendi yuksekliginden fazla kaymamis


@dataclass
class FallOutcome:
    track_id: int              # dusen iz (ilk FALL adayinin izi)
    fall_ts: float             # sahne zamani; sureler bununla
    fall_time: float | None    # duvar saati; olay eslesmesi bununla
    outcome: str               # "down" / "recovered" / "unknown"
    decided_ts: float
    metrics: dict[str, float]
    adopted: list[int]


@dataclass
class _Monitor:
    track_id: int
    fall_ts: float
    fall_time: float | None
    ref_height: float
    origin: int = 0            # dusen ilk iz; sonuc bununla anahtarlanir
    last_ts: float = 0.0
    last_centroid: np.ndarray | None = None
    last_posture: str = "lying"
    stand_since: float | None = None
    frames: int = 0            # dusmeden sonra islenen kare
    seen: int = 0              # bunlardan takip edilen izin gorulduigu
    obs: int = 0               # tum gozlemler (dusme karesi dahil)
    lying: int = 0
    max_ratio: float = 0.0
    lying_limb: list[float] = field(default_factory=list)
    adopted: list[int] = field(default_factory=list)


def _posture(feat, th: Thresholds, ref_height: float) -> str:
    if feat.body_tilt >= th.fall_tilt_deg:
        return "lying"
    if feat.height >= STAND_RATIO * ref_height:
        return "standing"
    return "other"


class PostFallMonitor:
    def __init__(self, decide_sec: float = DECIDE_SEC) -> None:
        self.decide_sec = decide_sec
        self._monitors: list[_Monitor] = []
        self._seen: dict[int, float] = {}    # iz -> son gorulme; devralmada "ilk kez" icin
        self._ts = 0.0

    def update(self, windows: dict[int, TrackWindow], candidates: list[Candidate],
               ts: float, th: Thresholds) -> list[FallOutcome]:
        self._ts = ts
        self._start(windows, candidates, th)
        self._adopt(windows)
        done = [o for m in list(self._monitors) if (o := self._step(m, windows, ts, th))]
        self._seen.update({tid: ts for tid in windows})
        for tid in [t for t, s in self._seen.items() if ts - s > STALE_SEC + EPS]:
            del self._seen[tid]
        return done

    def pending(self) -> list[tuple[int, float]]:
        return [(m.origin, self._ts - m.fall_ts) for m in self._monitors]

    def _start(self, windows, candidates, th) -> None:
        for cand in candidates:
            if cand.anomaly_type != "FALL":
                continue
            for tid in cand.track_ids:
                if tid not in windows or any(m.track_id == tid for m in self._monitors):
                    continue
                frames = windows[tid].frames
                upright = [f.height for f in frames if f.body_tilt < th.fall_tilt_deg]
                ref = max(upright) if upright else max(f.height for f in frames)
                self._monitors.append(_Monitor(tid, cand.ts, cand.event_time, float(ref), origin=tid))

    def _adopt(self, windows) -> None:
        followed = {m.track_id for m in self._monitors}
        for tid in sorted(windows):
            if tid in self._seen or tid in followed:
                continue
            c = windows[tid].last.centroid
            best, best_d = None, 0.0
            for m in self._monitors:
                if m.track_id in windows or m.last_centroid is None:
                    continue
                d = float(np.linalg.norm(c - m.last_centroid))
                if d <= ADOPT_DIST * m.ref_height and (best is None or d < best_d):
                    best, best_d = m, d
            if best is not None:
                followed.discard(best.track_id)
                best.track_id = tid
                best.adopted.append(tid)
                followed.add(tid)

    def _step(self, m: _Monitor, windows, ts: float, th: Thresholds) -> FallOutcome | None:
        if ts > m.fall_ts:
            m.frames += 1
        window = windows.get(m.track_id)
        if window is not None:
            f = window.last
            if ts > m.fall_ts:
                m.seen += 1
            m.obs += 1
            m.last_ts, m.last_centroid = ts, f.centroid
            m.last_posture = _posture(f, th, m.ref_height)
            m.max_ratio = max(m.max_ratio, float(f.height) / m.ref_height if m.ref_height > 0 else 0.0)
            if m.last_posture == "lying":
                m.lying += 1
                m.lying_limb.append(float(f.limb_speed))
            if m.last_posture == "standing":
                m.stand_since = ts if m.stand_since is None else m.stand_since
                # Yalniz GORULEN ayakta karede karar: 1 sn ayakta gorunup kaybolan
                # (yeniden yere yigilip algilanmayan) kisi "kalkti" sayilmasin.
                if ts - m.stand_since >= UPRIGHT_SEC - EPS:
                    return self._close(m, "recovered", ts)
            else:
                m.stand_since = None
        if ts - m.fall_ts >= self.decide_sec - EPS:
            return self._close(m, "down" if m.last_posture == "lying" else "unknown", ts)
        return None

    def _close(self, m: _Monitor, outcome: str, ts: float) -> FallOutcome:
        self._monitors.remove(m)
        metrics = {
            "decided_after_sec": ts - m.fall_ts,
            "last_seen_ago_sec": ts - m.last_ts,
            "seen_ratio": m.seen / m.frames if m.frames else 0.0,
            "lying_ratio": m.lying / m.obs if m.obs else 0.0,
            "max_height_ratio": m.max_ratio,
            "limb_speed_med": float(np.median(m.lying_limb)) if m.lying_limb else 0.0,
            "ref_height": m.ref_height,
        }
        if outcome == "recovered":
            metrics["recovered_after_sec"] = m.stand_since - m.fall_ts
        return FallOutcome(m.origin, m.fall_ts, m.fall_time, outcome, ts,
                           {k: float(v) for k, v in metrics.items()}, sorted(m.adopted))
