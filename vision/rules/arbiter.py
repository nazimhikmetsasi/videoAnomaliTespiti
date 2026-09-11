"""Asama 9.4: HybridArbiter — kural motoru + TCN modeli tek karar mercii.

`RuleEngine` ile AYNI imza (`__call__(windows) -> list[Candidate]`), boylece
`vision/run.py` tek satir degisir ve model yokken hicbir sey degismez.

Karar tablosu (docs/ASAMA9_PLAN.md SS9.4):

    model guveni < tcn_min_conf        -> yalnizca kural adaylari  (rule)
    model NORMAL disi + kural sessiz   -> model adayi              (model)
    model ve kural ayni tipte          -> tek aday, skor maksimum  (hybrid)
    ZONE_VIOLATION / LOITERING         -> her zaman kural          (rule)
    FIGHT                              -> model + YAKINLIK sarti     (model)

FIGHT'in ayri tutulmasi: model TEK izi siniflandirir, kavga ikili bir
olaydir. Bu yuzden modelin FIGHT oyu ancak iz YAKIN bir ciftin parcasiysa
aday uretir (`fight.close_pairs`).

Onceden model FIGHT'i tek basina HIC uretemiyordu; sart kuralin de ayni
tipte aday vermesiydi. Asama 11'de olculdu ki kuralin uzuv hizi sarti
FIGHT'i NORMAL'den ayirmiyor (0.5 ve ustu her esikte NORMAL orani daha
yuksek, en uzun ardisik seri 1 kare) -- yani calismayan bir kurala
baglanmak modelin FIGHT duyarliligini sifira cakiyordu (holdout F1: kural
0.12, model 0.00). Yakinlik sarti ise tutuyor. Ayrim buradan geliyor.
"""

from __future__ import annotations

import time

import numpy as np

from models.tcn import CHANNELS, MIN_POSE_RATIO, WINDOW, frame_vector
from vision.rules.engine import Candidate, RuleEngine
from vision.rules.fight import close_pairs
from vision.stages.features import TrackWindow

MODEL_TYPES = ("FALL", "RUN")     # model bunlari kosulsuz uretebilir
PAIR_TYPES = ("FIGHT",)           # bunlar icin ayrica YAKIN cift sarti aranir
RULE_ONLY = ("ZONE_VIOLATION", "LOITERING")
EVERY = 5      # kac karede bir model kosar (pencere 25 kare kayiyor)


def window_tensor(window: TrackWindow) -> np.ndarray | None:
    """TrackWindow -> (50, 53); pencere kisa veya cok pozsuzsa None."""
    frames = window.recent(WINDOW)
    if len(frames) < WINDOW:
        return None
    if sum(f.has_pose for f in frames) / WINDOW < MIN_POSE_RATIO:
        return None
    if any(f.bbox is None for f in frames):
        return None
    out = np.empty((WINDOW, CHANNELS), dtype=np.float32)
    prev = None
    for i, frame in enumerate(frames):
        dt = frame.ts - prev.ts if prev is not None else 0.0
        out[i] = frame_vector(frame.bbox, frame.keypoints,
                              None if prev is None else prev.bbox, dt)
        prev = frame
    return out


class HybridArbiter:
    """`classifier=None` verilirse davranis birebir `RuleEngine`dir."""

    def __init__(self, engine: RuleEngine, classifier=None, *,
                 min_conf: float = 0.60, every: int = EVERY) -> None:
        self.engine = engine
        self.classifier = classifier
        self.min_conf = min_conf
        self.every = every
        self.model_runs = 0          # vision/run.py raporu icin
        self.model_windows = 0
        self.model_ms: list[float] = []

    # RuleEngine ile ayni yuzey — run.py ve SettingsClient bunlara bakiyor.
    @property
    def thresholds(self):
        return self.engine.thresholds

    @thresholds.setter
    def thresholds(self, value) -> None:
        self.engine.thresholds = value

    @property
    def zones(self):
        return self.engine.zones

    def __call__(self, windows: dict[int, TrackWindow]) -> list[Candidate]:
        candidates = self.engine(windows)
        if self.classifier is None or not windows:
            return candidates
        idx = next(iter(windows.values())).last.idx
        if idx % self.every:
            return candidates
        verdicts = self._classify(windows)
        return self._merge(candidates, verdicts, windows)

    def _classify(self, windows: dict[int, TrackWindow]) -> dict[int, tuple[str, float]]:
        """Iz -> (sinif, olasilik). Tek toplu cagri; iz basina ayri cagri degil."""
        track_ids, tensors = [], []
        for track_id, window in windows.items():
            tensor = window_tensor(window)
            if tensor is not None:
                track_ids.append(track_id)
                tensors.append(tensor)
        if not tensors:
            return {}
        t0 = time.perf_counter()
        probs = self.classifier(np.stack(tensors))
        self.model_ms.append((time.perf_counter() - t0) * 1000)
        self.model_runs += 1
        self.model_windows += len(tensors)
        classes = self.classifier.classes
        return {track_id: (classes[int(row.argmax())], float(row.max()))
                for track_id, row in zip(track_ids, probs)}

    def _merge(self, candidates: list[Candidate], verdicts: dict[int, tuple[str, float]],
               windows: dict[int, TrackWindow]) -> list[Candidate]:
        merged: list[Candidate] = []
        boosted: set[int] = set()
        for cand in candidates:
            if cand.anomaly_type in RULE_ONLY:
                merged.append(cand)
                continue
            agrees = [tid for tid in cand.track_ids
                      if verdicts.get(tid, ("", 0.0))[0] == cand.anomaly_type
                      and verdicts[tid][1] >= self.min_conf]
            if agrees:
                conf = max(verdicts[tid][1] for tid in agrees)
                cand.decided_by = "hybrid"
                cand.score = max(cand.score, conf)
                cand.metrics = {**cand.metrics, "tcn_conf": conf}
                cand.thresholds_used = {**cand.thresholds_used,
                                        "tcn_min_conf": self.min_conf}
                boosted.update(agrees)
            merged.append(cand)

        pairs = close_pairs(windows, self.thresholds) if verdicts else set()
        for track_id, (label, conf) in verdicts.items():
            if conf < self.min_conf or track_id in boosted:
                continue
            if label in PAIR_TYPES:
                if track_id not in pairs:
                    continue        # kavga ikili bir olaydir: yakin cift yoksa aday yok
            elif label not in MODEL_TYPES:
                continue
            last = windows[track_id].last
            merged.append(Candidate(
                anomaly_type=label,
                track_ids=[track_id],
                score=conf,
                idx=last.idx,
                ts=last.ts,
                metrics={"tcn_conf": conf},
                thresholds_used={"tcn_min_conf": self.min_conf},
                decided_by="model",
            ))
        return merged
