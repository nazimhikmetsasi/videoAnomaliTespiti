"""LOITERING kurali: bolgede uzun kalis veya sabit dolanma (PLAN.md #4).

Iz penceresi (RETAIN_SEC, 2 sn) loiter_sec'i (varsayilan 30 sn) tutamaz;
bu yuzden kural kendi girisini (enter_ts) ve cipasini (anchor) kendi
durumunda saklar. Iz kaybolunca (STALE_SEC) durum duser. Ayni iz
tetikledikten sonra RETRIGGER_SEC boyunca susar; yoksa 30 sn'lik bekleyis
her karede yeni aday uretir.

Iki mod, bolge tanimli olup olmamasina gore SABIT secilir (kare kare
degil): bolge varsa ayagin bolgede kalisi, yoksa merkezin kendi
yuksekliginden fazla kaymamasi.

Kisa sapmalar sayaci SIFIRLAMAZ. Once tek bir kare yetiyordu ve kural
pratikte hic tetiklenmiyordu -- olculdu (eval/loiter_probe.py, zone_01):
iz 32.5 sn kesintisiz goruldu, ama ayak noktasi bolge sinirinda tek kare
(0.04 sn) disari tasip birikimi sifirladigi icin bolgede en uzun aralik-
siz kalis 11.7 sn cikti. Kapinin onunde hareketsiz duran kisi, klibin
kendi ihlal cercevesi kirmiziyken 1.88 sn "bolge disi" sayildi.

Tolerans STALE_SEC'in KENDISIDIR, bu klipten secilmedi: kural izin
tamamen kaybolmasini zaten 3.6 sn tolere ediyor. Kisiyi 3.6 sn hic
gormemeyi "hala orada" sayip ayak noktasinin tek kare sinir disina
kaymasini "ayrildi" saymak tutarsizdi; ikisi de ayni anlama gelir:
varligi su an dogrulayamiyorum.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from vision.rules.engine import Candidate, Thresholds, Zone
from vision.stages.features import EPS, STALE_SEC, FrameFeatures, TrackWindow

RETRIGGER_SEC = 10.0


@dataclass
class _State:
    enter_ts: float
    anchor: np.ndarray
    last_seen_ts: float
    last_trigger_ts: float | None = None
    # Bolge disina / cipadan uzaga ilk cikilan an; None = su an yerinde.
    away_since_ts: float | None = None


class LoiterRule:
    def __init__(self, zones: Sequence[Zone] = (),
                 clock: Callable[[], float] = time.time) -> None:
        self.zones = list(zones)
        self.clock = clock      # saat araligi duvar saatine bakar (bkz. zone.py)
        self._state: dict[int, _State] = {}

    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None:
        last = window.last
        self._prune(last.ts)

        st = self._state.get(window.track_id)
        if self.zones:
            zone = self._matching_zone(last)
            still = zone is not None
        else:
            zone = None
            still = st is not None and self._drift(last, st.anchor) <= last.height

        if st is None:
            # Bolge modunda sayac bolgeye GIRINCE baslar; disarida gecen sure
            # bekleme sayilmaz. Cipa modunda ilk gorulme cipanin kendisidir.
            if self.zones and zone is None:
                return None
            self._state[window.track_id] = _State(last.ts, last.centroid, last.ts)
            return None

        st.last_seen_ts = last.ts
        if not still:
            if st.away_since_ts is None:
                st.away_since_ts = last.ts
            if last.ts - st.away_since_ts > STALE_SEC + EPS:
                # Gercekten ayrildi: bolge modunda sayac sifirlanir, cipa
                # modunda yeni konum yeni cipa olur.
                if self.zones:
                    del self._state[window.track_id]
                else:
                    self._state[window.track_id] = _State(last.ts, last.centroid, last.ts)
            return None      # yerinde degilken aday uretilmez
        st.away_since_ts = None

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
            if zone.zone_type == "restricted_hours" and not zone.active_at(self.clock()):
                continue
            if zone.contains(feat.foot):
                return zone
        return None

    @staticmethod
    def _drift(feat: FrameFeatures, anchor: np.ndarray) -> float:
        return float(np.linalg.norm(feat.centroid - anchor))

    def _prune(self, ts: float) -> None:
        stale = [tid for tid, st in self._state.items() if ts - st.last_seen_ts > STALE_SEC + EPS]
        for tid in stale:
            del self._state[tid]
