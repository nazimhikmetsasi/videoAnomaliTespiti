"""One-Euro filtresi ile keypoint duzlestirme (PLAN.md zayif nokta 5).

Ham keypoint dogrudan hiz hesaplarina girerse dedektor titremesi hiza
karisir ve yanlis alarm uretir. One-Euro dusuk hizda agir, yuksek hizda
hafif filtreler -- durup dururken titremeyi keser, gercek harekette
gecikme yaratmaz.

Vektorlestirilmis: iz basina durum (17, 2) dizileridir (x_prev, dx_prev)
arti tek bir t_prev. Keypoint basina ayri filtre nesnesi (17 x 2 = 34
nesne/iz) burada gereksiz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vision.stages.tracker import Track

STALE_FRAMES = 90     # bu kadar kare gorulmeyen izin durumu duser


@dataclass
class _State:
    x_prev: np.ndarray       # (17, 2)
    dx_prev: np.ndarray      # (17, 2)
    t_prev: float
    last: np.ndarray         # (17, 3) -- son duzlestirilmis deger (hold icin)
    age: int = 0


def _alpha(cutoff: np.ndarray | float, dt: float) -> np.ndarray | float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class Smoother:
    def __init__(self, *, min_cutoff: float = 1.0, beta: float = 0.05,
                 d_cutoff: float = 1.0, kp_conf: float = 0.5) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.kp_conf = kp_conf
        self._state: dict[int, _State] = {}

    def __call__(self, tracks: list[Track], ts: float) -> list[Track]:
        """Her izin keypoints_smoothed alanini doldurur, ayni listeyi dondurur."""
        seen: set[int] = set()
        for track in tracks:
            if track.keypoints is None:
                continue
            seen.add(track.track_id)
            track.keypoints_smoothed = self._smooth(track.track_id, track.keypoints, ts)
        self._cleanup(seen)
        return tracks

    def _smooth(self, track_id: int, raw: np.ndarray, ts: float) -> np.ndarray:
        st = self._state.get(track_id)
        if st is None:
            # Ilk gorunum: ham deger aynen kopyalanir, durum kurulur.
            smoothed = raw.copy()
            self._state[track_id] = _State(
                x_prev=raw[:, :2].copy(),
                dx_prev=np.zeros((17, 2), dtype=np.float64),
                t_prev=ts, last=smoothed,
            )
            return smoothed

        dt = ts - st.t_prev
        if dt <= 0:
            smoothed = raw.copy()
            st.x_prev = raw[:, :2].copy()
            st.dx_prev = np.zeros((17, 2), dtype=np.float64)
            st.t_prev, st.last, st.age = ts, smoothed, 0
            return smoothed

        x = raw[:, :2]
        dx = (x - st.x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * st.dx_prev
        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        a = _alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * st.x_prev

        # Dusuk guvenli keypoint filtreye sokulmaz, son duzlestirilmis deger
        # korunur. Guven sutunu ham degeriyle tasinir.
        mask = raw[:, 2] >= self.kp_conf
        smoothed = st.last.copy()
        smoothed[mask, :2] = x_hat[mask]
        smoothed[:, 2] = raw[:, 2]

        st.x_prev[mask] = x_hat[mask]
        st.dx_prev[mask] = dx_hat[mask]
        st.t_prev, st.last, st.age = ts, smoothed, 0
        return smoothed

    def _cleanup(self, seen: set[int]) -> None:
        for track_id in list(self._state):
            if track_id in seen:
                continue
            st = self._state[track_id]
            st.age += 1
            if st.age > STALE_FRAMES:
                del self._state[track_id]
