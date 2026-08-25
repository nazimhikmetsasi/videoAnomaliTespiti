"""On isleme: letterbox + CLAHE.

v1'de CLAHE nesnesi her karede yeniden yaratiliyordu (PLAN.md zayif nokta 6).
Burada bir kez kurulur ve yeniden kullanilir.

Letterbox en-boy oranini korur; basit `resize` insani yatay/dikey ezer ve
bbox yuksekligine normalize edilen tum esikleri (hiz, mesafe) bozardi.

CLAHE letterbox'tan SONRA uygulanir: 960x540 uzerinde calismak 1080p
uzerinde calismaktan yaklasik dort kat ucuzdur ve tespit yine kucultulmus
kare uzerinde yapilir.

CLAHE olcumde kare basina 8-9 ms tutuyor — 25 FPS butcesinin (40 ms) besde
biri. Iyi isikta hicbir sey kazandirmadigi icin kosullu calisir: kare zaten
yeterli kontrasttaysa atlanir. Kapi maliyeti ~0.1 ms (1/8 kucultulmus gri
karenin standart sapmasi).
"""

from __future__ import annotations

import cv2
import numpy as np

FRAME_W, FRAME_H = 960, 540
PAD_VALUE = 114          # ultralytics letterbox ile ayni gri
CLAHE_CLIP = 2.0
CLAHE_TILE = (8, 8)
# Iyi isikli karede gri standart sapma tipik olarak 50-70; dusuk isik ve sisli
# goruntude 40'in altina iner. Kamera bazinda Asama 5'te ayarlanabilir olacak.
CLAHE_MIN_STD = 45.0


def letterbox(image: np.ndarray, width: int = FRAME_W, height: int = FRAME_H) -> np.ndarray:
    """En-boy oranini koruyarak olceklendirir, kalani gri ile doldurur."""
    h, w = image.shape[:2]
    scale = min(width / w, height / h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(image, (new_w, new_h), interpolation=interp)

    if (new_w, new_h) == (width, height):
        return resized

    canvas = np.full((height, width, 3), PAD_VALUE, dtype=np.uint8)
    top, left = (height - new_h) // 2, (width - new_w) // 2
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas


class Preprocessor:
    """Kare -> sabit boyutlu, kontrasti duzeltilmis temiz kare."""

    def __init__(
        self,
        width: int = FRAME_W,
        height: int = FRAME_H,
        *,
        clahe: bool = True,
        clip_limit: float = CLAHE_CLIP,
        tile_grid: tuple[int, int] = CLAHE_TILE,
        min_std: float = CLAHE_MIN_STD,
    ) -> None:
        self.width = width
        self.height = height
        self.min_std = min_std
        # Bir kez kurulur — dongude yeniden yaratilmaz.
        self._clahe = (
            cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid) if clahe else None
        )
        self.clahe_applied = 0

    def needs_clahe(self, image: np.ndarray) -> bool:
        """Kare kontrast bakimindan zayif mi. Ucuz olmasi icin 1/8 boyutta bakilir.

        Olcum letterbox ONCESI ham karede yapilir: dolgu bantlari sabit renk
        oldugu icin standart sapmayi yapay olarak dusurur ve CLAHE'yi gereksiz
        yere tetiklerdi.
        """
        small = cv2.resize(image, (self.width // 8, self.height // 8),
                           interpolation=cv2.INTER_NEAREST)
        return float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).std()) < self.min_std

    def __call__(self, image: np.ndarray) -> np.ndarray:
        apply_clahe = self._clahe is not None and self.needs_clahe(image)
        out = letterbox(image, self.width, self.height)
        if not apply_clahe:
            return out
        self.clahe_applied += 1
        # Yalnizca parlaklik kanali esitlenir; renk kaymasi olmaz.
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = self._clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
