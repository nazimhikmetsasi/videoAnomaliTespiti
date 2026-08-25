"""Olcek-normalize kinematik oznitelikler (PLAN.md zayif nokta 4).

Hiz/mesafe bbox yuksekligine bolunur -- kameradan ve mesafeden bagimsiz.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass

import numpy as np

from vision.stages.tracker import Track

KP = {"nose": 0, "l_sho": 5, "r_sho": 6, "l_wri": 9, "r_wri": 10,
      "l_hip": 11, "r_hip": 12, "l_knee": 13, "r_knee": 14,
      "l_ank": 15, "r_ank": 16}          # COCO-17
STALE_FRAMES = 90      # bu kadar kare gorulmeyen izin penceresi duser
LIMB_HIST = 3           # limb_speed'in baktigi yer degistirme penceresi (kare)
LIMB_KEYPOINTS = (KP["l_wri"], KP["r_wri"], KP["l_ank"], KP["r_ank"])

def _avg_point(kp: np.ndarray, idxs: tuple[int, ...], conf_th: float) -> np.ndarray | None:
    """Guveni yeterli noktalarin ortalamasi; hicbiri yoksa None."""
    pts = [kp[i, :2] for i in idxs if kp[i, 2] >= conf_th]
    return np.mean(pts, axis=0) if pts else None

def _angle_deg(v1: np.ndarray, v2: np.ndarray) -> float:
    denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
    if denom < 1e-6:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / denom, -1.0, 1.0))))

@dataclass
class FrameFeatures:
    idx: int
    ts: float
    has_pose: bool
    height: float             # bbox yuksekligi, px -- normalizasyon birimi
    centroid: np.ndarray      # (2,) px -- bbox merkezi (SS10.2, asla mid_hip degil)
    foot: np.ndarray          # (2,) 0-1 normalize -- mid_ankle, yoksa bbox alt orta
    aspect: float             # bbox genislik / yukseklik
    norm_speed: float         # |yatay hiz| / height (1/sn)
    norm_vy: float            # dikey hiz / height, ASAGI POZITIF (1/sn)
    body_tilt: float          # govde dikeyden sapma, derece -- max(skeleton, box). Kural bunu kullanir (SS10.1)
    spine_angle: float        # yalnizca iskeletten; bilinmiyorsa -1.0. Kural KULLANMAZ, telemetri/tez icin
    knee_angle: float         # kalca-diz-bilek acisi, derece (180 = duz bacak)
    limb_speed: float         # bilek/ayak bilegi icinde en yuksek normalize hiz

class TrackWindow:
    """Tek izin son `window_frames` karesi."""

    def __init__(self, track_id: int, maxlen: int) -> None:
        self.track_id, self.frames = track_id, collections.deque(maxlen=maxlen)
    @property
    def last(self) -> FrameFeatures:
        return self.frames[-1]
    def recent(self, n: int) -> list[FrameFeatures]:
        return list(self.frames)[-n:]

class FeatureEngine:
    def __init__(self, *, window_frames: int = 50, kp_conf: float = 0.5,
                 velocity_lookback: int = 5) -> None:
        self.window_frames, self.kp_conf, self.velocity_lookback = window_frames, kp_conf, velocity_lookback
        self._windows: dict[int, TrackWindow] = {}
        self._kp_hist: dict[int, collections.deque[tuple[float, np.ndarray]]] = {}
        self._age: dict[int, int] = {}

    def __call__(self, tracks: list[Track], idx: int, ts: float,
                 frame_shape: tuple[int, int]) -> dict[int, TrackWindow]:
        """Pencereleri gunceller, BU karede gorulen izlerin pencerelerini dondurur."""
        h, w = frame_shape[0], frame_shape[1]
        seen: dict[int, TrackWindow] = {}
        for track in tracks:
            window = self._windows.setdefault(
                track.track_id, TrackWindow(track.track_id, self.window_frames))
            window.frames.append(self._compute(track, window, idx, ts, h, w))
            self._age[track.track_id] = 0
            seen[track.track_id] = window
        self._cleanup(seen.keys())
        return seen

    def _compute(self, track: Track, window: TrackWindow, idx: int, ts: float,
                 h: int, w: int) -> FrameFeatures:
        kp = track.keypoints_smoothed if track.keypoints_smoothed is not None else track.keypoints
        has_pose = kp is not None
        height = track.height
        x1, y1, x2, y2 = track.bbox
        aspect = (x2 - x1) / height if height > 0 else 0.0
        # box_tilt: bbox genislik/yukseklik acisi, derece -- keypoint gerekmez, her zaman var.
        box_tilt = math.degrees(math.atan2(x2 - x1, height)) if height > 0 else 0.0
        # SS10.2: centroid HER ZAMAN bbox merkezi -- mid_hip kalca guveni dusunce
        # sicrardi (olculen 5.61 sn: nspeed 2.46/nvy -2.79, gercek hareket yok).
        centroid = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
        if not has_pose:
            foot = np.array([(x1 + x2) / 2 / w, y2 / h])
            # Hiz/aci 0.0 (RuleEngine pozsuz kareyi zaten disliyor); body_tilt
            # bbox'tan bile hesaplanir (SS10.5#4), keypoint gerektirmez.
            return FrameFeatures(idx, ts, False, height, centroid, foot, aspect,
                                  0.0, 0.0, box_tilt, -1.0, 180.0, 0.0)
        mid_ank = _avg_point(kp, (KP["l_ank"], KP["r_ank"]), self.kp_conf)
        foot_px = mid_ank if mid_ank is not None else np.array([(x1 + x2) / 2, y2])
        foot = np.array([foot_px[0] / w, foot_px[1] / h])
        norm_speed, norm_vy = self._velocity(window, centroid, height, ts)
        spine = self._spine_angle(kp)
        # SS10.1: kameraya dogru dusende kalca->omuz dikeyde kalir, spine bunu
        # goremez (fall_01 tepe 20.2 derece, esik 45); box_tilt her zaman var.
        body_tilt = box_tilt if spine < 0.0 else max(box_tilt, spine)
        return FrameFeatures(idx, ts, True, height, centroid, foot, aspect, norm_speed, norm_vy,
                              body_tilt, spine, self._knee_angle(kp),
                              self._limb_speed(track.track_id, kp, height, ts))

    def _velocity(self, window: TrackWindow, centroid: np.ndarray, height: float,
                  ts: float) -> tuple[float, float]:
        # velocity_lookback kare geriden: kareden kareye tek karelik gurultu hizi ikiye katliyor.
        frames = window.frames
        # Pencere dolmadan hiz UretILMEZ. Kisa pencerede en eski kareye
        # bakmak dt'yi tek kareye kadar dusuruyor ve iz dogarken kutunun
        # oturma titremesi hiz gibi okunuyordu: normal_01 klibi 0.4 sn'de
        # 25 RUN adayi uretiyordu. Bedeli iz basina 5 karelik (0.2 sn) sessizlik.
        if len(frames) < self.velocity_lookback or height <= 0:
            return 0.0, 0.0
        old = frames[-self.velocity_lookback]
        dt = ts - old.ts
        if dt <= 0:
            return 0.0, 0.0
        return abs(centroid[0] - old.centroid[0]) / dt / height, (centroid[1] - old.centroid[1]) / dt / height

    def _spine_angle(self, kp: np.ndarray) -> float:
        mid_hip = _avg_point(kp, (KP["l_hip"], KP["r_hip"]), self.kp_conf)
        mid_sho = _avg_point(kp, (KP["l_sho"], KP["r_sho"]), self.kp_conf)
        if mid_hip is None or mid_sho is None:
            return -1.0    # bilinmiyor -- 0.0 "dimdik" ile karisirdi, sessiz yanlis negatif (SS10.1)
        return math.degrees(math.atan2(abs(mid_sho[0] - mid_hip[0]), abs(mid_sho[1] - mid_hip[1]) + 1e-9))

    def _knee_angle(self, kp: np.ndarray) -> float:
        angles = []
        for hip_k, knee_k, ank_k in (("l_hip", "l_knee", "l_ank"), ("r_hip", "r_knee", "r_ank")):
            hip, knee, ank = KP[hip_k], KP[knee_k], KP[ank_k]
            if min(kp[hip, 2], kp[knee, 2], kp[ank, 2]) < self.kp_conf:
                continue
            angles.append(_angle_deg(kp[hip, :2] - kp[knee, :2], kp[ank, :2] - kp[knee, :2]))
        return min(angles) if angles else 180.0

    def _limb_speed(self, track_id: int, kp: np.ndarray, height: float, ts: float) -> float:
        hist = self._kp_hist.setdefault(track_id, collections.deque(maxlen=LIMB_HIST))
        speed = 0.0
        if hist and height > 0:
            old_ts, old_kp = hist[0]
            dt = ts - old_ts
            if dt > 0:
                for i in LIMB_KEYPOINTS:
                    if old_kp[i, 2] >= self.kp_conf and kp[i, 2] >= self.kp_conf:
                        speed = max(speed, float(np.linalg.norm(kp[i, :2] - old_kp[i, :2])) / dt / height)
        hist.append((ts, kp))
        return speed

    def _cleanup(self, seen) -> None:
        seen = set(seen)
        for track_id in list(self._windows):
            if track_id in seen:
                continue
            self._age[track_id] = self._age.get(track_id, 0) + 1
            if self._age[track_id] > STALE_FRAMES:
                del self._windows[track_id], self._age[track_id]
                self._kp_hist.pop(track_id, None)
