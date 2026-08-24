"""Asama 0 dogrulama betigi.

Ne olcer:
  1. torch CUDA derlemesi mi, GPU gorunuyor mu
  2. yolov8s-pose ve yolov8n-pose GPU'da yukleniyor ve kisi buluyor mu
  3. Kare basina cikarim suresi (medyan) ve tahmini FPS
  4. Model basina VRAM kullanimi (agirliklar dahil)

Neden iki model: PLAN.md risk 1 — 4 GB VRAM'de coklu kamerada 's' sigmayabilir.
Karari tahmine degil olcume dayandirmak icin ikisi de olculur.

Test karesi ultralytics ile birlikte gelen bus.jpg — icinde gercek insanlar
var, yani sure olcumu kadar modelin dogru calistigi da kanitlanir. Ag
baglantisi gerekmez.

Calistirma:
    venv\\Scripts\\python.exe scripts/check_gpu.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"
FRAME_W, FRAME_H = 960, 540
WARMUP_RUNS = 5
TIMED_RUNS = 30
# FP16. Ultralytics 8.4'te half=True kullanimdan kalkti, yerine quantize=16.
QUANTIZE_FP16 = 16


def load_test_frame() -> tuple[np.ndarray, str]:
    """Ultralytics ile gelen bus.jpg — gercek insan iceren yerel gorsel."""
    import cv2
    from ultralytics.utils import ASSETS

    sample = Path(ASSETS) / "bus.jpg"
    if sample.exists():
        img = cv2.imread(str(sample))
        if img is not None:
            return cv2.resize(img, (FRAME_W, FRAME_H)), "bus.jpg (gercek insanlar)"

    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (FRAME_H, FRAME_W, 3), dtype=np.uint8)
    return noise, "sentetik gurultu (tespit sayisi anlamsiz)"


def check_torch() -> bool:
    import torch

    print("=" * 62)
    print("1. TORCH / CUDA")
    print("=" * 62)
    print(f"  torch surumu      : {torch.__version__}")
    print(f"  CUDA derlemesi    : {torch.version.cuda or 'YOK (CPU derlemesi)'}")
    print(f"  cuda.is_available : {torch.cuda.is_available()}")

    if not torch.cuda.is_available():
        print("\n  HATA: CUDA gorunmuyor. cu121 wheel kurulu mu?")
        print("  Cozum: pip install torch torchvision "
              "--index-url https://download.pytorch.org/whl/cu121")
        return False

    props = torch.cuda.get_device_properties(0)
    print(f"  GPU               : {props.name}")
    print(f"  VRAM              : {props.total_memory / 1024**2:.0f} MiB")
    print(f"  Compute capability: {props.major}.{props.minor}")
    return True


def benchmark(model_name: str, frame: np.ndarray) -> dict | None:
    import torch
    from ultralytics import YOLO

    weights = MODELS_DIR / model_name
    print(f"\n  --- {model_name} ---")

    # Agirliklarin VRAM'i de sayilsin diye sayaci yuklemeden ONCE sifirla.
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    try:
        model = YOLO(str(weights) if weights.exists() else model_name)
        model.to("cuda")
    except Exception as exc:
        print(f"  HATA: model yuklenemedi: {exc}")
        return None

    for _ in range(WARMUP_RUNS):
        model.predict(frame, device="cuda", quantize=QUANTIZE_FP16, verbose=False)
    torch.cuda.synchronize()

    durations = []
    detected = 0
    for _ in range(TIMED_RUNS):
        start = time.perf_counter()
        results = model.predict(frame, device="cuda", quantize=QUANTIZE_FP16, verbose=False)
        torch.cuda.synchronize()
        durations.append((time.perf_counter() - start) * 1000)
        boxes = results[0].boxes
        detected = 0 if boxes is None else len(boxes)

    median_ms = statistics.median(durations)
    peak_mib = torch.cuda.max_memory_allocated() / 1024**2

    print(f"  kare basina       : {median_ms:.1f} ms (medyan, {TIMED_RUNS} kosu)")
    print(f"  tahmini FPS       : {1000 / median_ms:.1f}")
    print(f"  tepe VRAM         : {peak_mib:.0f} MiB")
    print(f"  bulunan kisi      : {detected}")

    del model
    torch.cuda.empty_cache()

    return {
        "model": model_name,
        "median_ms": median_ms,
        "fps": 1000 / median_ms,
        "peak_mib": peak_mib,
        "detected": detected,
    }


def main() -> int:
    if not check_torch():
        return 1

    frame, frame_kind = load_test_frame()
    real_frame = not frame_kind.startswith("sentetik")

    print("\n" + "=" * 62)
    print("2. MODEL CIKARIM OLCUMU")
    print("=" * 62)
    print(f"  test karesi       : {FRAME_W}x{FRAME_H} — {frame_kind}")

    results = [r for r in (benchmark(m, frame)
                           for m in ("yolov8s-pose.pt", "yolov8n-pose.pt")) if r]

    if not results:
        print("\n  HATA: hicbir model calismadi.")
        return 1

    print("\n" + "=" * 62)
    print("3. OZET")
    print("=" * 62)
    print(f"  {'model':<20} {'ms':>8} {'FPS':>8} {'VRAM MiB':>10} {'kisi':>6}")
    for r in results:
        print(f"  {r['model']:<20} {r['median_ms']:>8.1f} {r['fps']:>8.1f} "
              f"{r['peak_mib']:>10.0f} {r['detected']:>6}")

    best = results[0]
    if best["fps"] >= 25:
        print(f"\n  SONUC: {best['model']} tek kamerada 25 FPS hedefini karsiliyor.")
    elif best["fps"] >= 15:
        print(f"\n  SONUC: {best['model']} 15-25 FPS araliginda. Tek kamera icin "
              "yeterli, coklu kamerada 'n' modeline dusulmeli.")
    else:
        print(f"\n  SONUC: {best['model']} 15 FPS altinda. 'n' modeli veya "
              "daha dusuk cozunurluk gerekli.")

    # Gercek karede kisi bulunamadiysa sure olcumu gecerli ama model bozuk demektir.
    if real_frame and best["detected"] == 0:
        print("  HATA: gercek karede hic kisi bulunamadi — model dogru calismiyor.")
        return 1
    if not real_frame:
        print("  NOT: sentetik kare kullanildi — sureler gecerli, tespit sayisi "
              "anlamli degil.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
