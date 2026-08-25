"""Model agirliklarini `models/` altina indirir.

Agirliklar `.gitignore`'da (`*.pt`, `*.onnx`) — depo klonlandiktan sonra bu
betik bir kez calistirilir.

    venv/Scripts/python.exe scripts/fetch_models.py

Neler iniyor:

- `yolo26s-pose.pt`   tek kamera varsayilani
- `yolo26n-pose.pt`   coklu kamera / dusuk butce yedegi
- `yolo26s-reid.onnx` gorunum (ReID) agi — YOLO26 end2end oldugu icin
  dedektorun bedava govde oznitelikleri BoT-SORT'a baglanamiyor
- `yolov8s-pose.pt`   ablation karsilastirmasi (tez tablosu)
"""

from __future__ import annotations

import sys
from pathlib import Path

MODELS = (
    "yolo26s-pose.pt",
    "yolo26n-pose.pt",
    "yolo26s-reid.onnx",
    "yolov8s-pose.pt",
)
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def main() -> int:
    from ultralytics.utils.downloads import attempt_download_asset

    MODELS_DIR.mkdir(exist_ok=True)
    for name in MODELS:
        target = MODELS_DIR / name
        if target.exists():
            print(f"  [VAR]  {name}")
            continue
        # attempt_download_asset calisma dizinine yazar; oraya gecici olarak gecilir.
        attempt_download_asset(str(target))
        status = "[INDI]" if target.exists() else "[HATA]"
        print(f"  {status} {name}")

    missing = [n for n in MODELS if not (MODELS_DIR / n).exists()]
    if missing:
        print(f"\n  inmeyen: {', '.join(missing)}")
        return 1
    print(f"\n  {len(MODELS)}/{len(MODELS)} model hazir: {MODELS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
