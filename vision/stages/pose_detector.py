"""YOLOv8s-pose ile tek gecisli kutu + iskelet cikarimi.

v1 ayni kareye once detect sonra pose modeli kosuyordu (PLAN.md zayif nokta 1).
Pose modeli kutuyu zaten uretir; tek gecis yeter.

Toplu (batch) cikarim bastan destekleniyor: `__call__` kare listesi alir.
Coklu kamera Asama 10'da ayni cagriya N kare vererek olceklenir, kamera basina
ayri process ve model kopyasi acilmaz.

ReID ozellikleri: `botsort.yaml` icinde `model: auto` secildiginde BoT-SORT,
dedektorun kendi govde ozniteliklerini gorunum vektoru olarak kullanir — ek
model, ek VRAM ve ek cikarim maliyeti olmadan ReID. Ultralytics bu ozellikleri
yalnizca `model.track()` yolunda toplar; biz toplu cikarimi kendimiz
surdugumuz icin ayni on-kancayi burada kuruyoruz.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.nn.modules.head import Detect

DEFAULT_WEIGHTS = "models/yolov8s-pose.pt"
QUANTIZE_FP16 = 16       # ultralytics 8.4'te half=True kullanimdan kalkti
PERSON_CLASS = 0


class PoseDetector:
    """Kare listesi -> ultralytics Results listesi (kutu + 17 keypoint)."""

    def __init__(
        self,
        weights: str | Path = DEFAULT_WEIGHTS,
        *,
        device: str = "cuda",
        conf: float = 0.35,
        imgsz: int = 960,
        fp16: bool = True,
        reid_feats: bool = True,
    ) -> None:
        self.device = device
        self.conf = conf
        self.imgsz = imgsz
        self.quantize = QUANTIZE_FP16 if fp16 else None
        self.reid_feats = reid_feats

        path = Path(weights)
        self.model = YOLO(str(path) if path.exists() else str(weights))
        self.model.to(device)

        # Isinma cagrisi predictor'u yaratir (kanca ona takilir) ve CUDA
        # baslatma maliyetini olcum dongusunun disinda birakir.
        self._predict([np.zeros((540, 960, 3), dtype=np.uint8)])
        self._hook = None
        if reid_feats:
            self._register_feats_hook()

    def _predict(self, frames: list[np.ndarray]):
        kwargs = dict(
            device=self.device,
            conf=self.conf,
            imgsz=self.imgsz,
            classes=[PERSON_CLASS],
            verbose=False,
        )
        if self.quantize is not None:
            kwargs["quantize"] = self.quantize
        return self.model.predict(frames, **kwargs)

    def _register_feats_hook(self) -> None:
        """Detect kafasinin girdisini yakalar; postprocess bunu `result.feats`
        olarak dondurur. Kanca takilamazsa ReID sessizce devre disi kalir."""
        predictor = getattr(self.model, "predictor", None)
        if predictor is None:
            return
        inner = getattr(predictor.model, "model", None)
        if not isinstance(inner, torch.nn.Module):
            return
        head = inner.model[-1]
        if not isinstance(head, Detect) or getattr(head, "end2end", False):
            return

        def pre_hook(_module, inputs):
            predictor._feats = list(inputs[0])

        predictor._feats = None
        self._hook = head.register_forward_pre_hook(pre_hook)

    @property
    def has_reid_feats(self) -> bool:
        return self._hook is not None

    def __call__(self, frames: list[np.ndarray]):
        return self._predict(frames)

    def close(self) -> None:
        if self._hook is not None:
            self._hook.remove()
            self._hook = None
