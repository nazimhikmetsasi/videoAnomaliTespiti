"""`tcn_min_conf` esigini tarar: yanlis alarmi kesmek gercek olayi oldururmu?

Olculen bulgu (eval/domain_gap.py): modelin pilot kliplerdeki NORMAL DISI
tahminleri esigin hemen ustunde kumeleniyor (ortalama olasilik 0.59-0.70),
NORMAL tahminleri ise emin (0.853). Calisan esik 0.60, yani tam o bandin
altinda.

Bu, alan farkindan once bir ESIK KALIBRASYONU sorunu oldugunu dusundurur --
ve dogruysa yeniden egitim gerektirmez. Ama esigi yukseltmek dogrulama
kumesindeki gercek olaylari da kesebilir; bu betik iki tarafi YAN YANA
olcer ve karari sayiya birakir.

Dogrulama kumesi klip bazinda ayrilmistir (models/tcn.load_split,
VAL_EVERY=5); egitimde gorulen klipler buraya dusmez.

    venv/Scripts/python.exe -m eval.conf_sweep
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.tcn import CLASSES, TCNClassifier, load_split  # noqa: E402

NORMAL = CLASSES.index("NORMAL")
ESIKLER = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90]


def val_olasiliklari(root: Path, clf: TCNClassifier) -> tuple[np.ndarray, np.ndarray]:
    _, _, x_val, y_val = load_split(root)
    return clf(x_val), y_val


def pilot_olasiliklari(clips_dir: Path, clf: TCNClassifier, model: str) -> np.ndarray:
    from eval.domain_gap import pilot_pencereleri
    from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector

    clips = sorted(clips_dir.glob("*.mp4"))
    if not clips:
        return np.zeros((0, len(CLASSES)), dtype=np.float32)
    pencereler = pilot_pencereleri(clips, PoseDetector(model or DEFAULT_WEIGHTS))
    if not pencereler.size:
        return np.zeros((0, len(CLASSES)), dtype=np.float32)
    return clf(pencereler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="tcn_min_conf esik taramasi")
    parser.add_argument("--sequences", default="data/sequences")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)

    clf = TCNClassifier()
    val_p, val_y = val_olasiliklari(Path(args.sequences), clf)
    pilot_p = pilot_olasiliklari(Path(args.clips), clf, args.model)

    val_tahmin = val_p.argmax(axis=1)
    val_guven = val_p.max(axis=1)
    # "Gercek olay" = dogrulama kumesindeki NORMAL DISI pencereler.
    gercek_olay = val_y != NORMAL
    toplam_olay = int(gercek_olay.sum())

    pilot_tahmin = pilot_p.argmax(axis=1) if pilot_p.size else np.zeros(0, int)
    pilot_guven = pilot_p.max(axis=1) if pilot_p.size else np.zeros(0)

    print(f"\n  dogrulama: {len(val_y)} pencere ({toplam_olay} gercek olay)")
    print(f"  pilot    : {len(pilot_tahmin)} pencere\n")
    print(f"  {'esik':>6} {'yakalanan olay':>15} {'duyarlilik':>11} "
          f"{'val yanlis alarm':>17} {'pilot yanlis alarm':>19}")

    for esik in ESIKLER:
        # Hakem mantigi (vision/rules/arbiter.py): tahmin NORMAL disi VE
        # guven esigin ustundeyse aday uretilir.
        val_alarm = (val_tahmin != NORMAL) & (val_guven >= esik)
        yakalanan = int((val_alarm & gercek_olay).sum())
        val_yanlis = int((val_alarm & ~gercek_olay).sum())
        duyarlilik = yakalanan / toplam_olay if toplam_olay else 0.0

        pilot_yanlis = int(((pilot_tahmin != NORMAL) & (pilot_guven >= esik)).sum())
        isaret = "  <- calisan esik" if abs(esik - 0.60) < 1e-9 else ""
        print(f"  {esik:6.2f} {yakalanan:15d} {duyarlilik:11.3f} "
              f"{val_yanlis:17d} {pilot_yanlis:19d}{isaret}")

    print("\n  Pilot klipler agirlikli olarak NORMAL davranis icerir; oradaki")
    print("  her NORMAL disi guclu tahmin yanlis alarm adayidir. Dogrulama")
    print("  kumesi ise egitim ALANINDADIR -- iki sutun ayni birimde degildir,")
    print("  karsilastirilan sey EGILIMDIR: esik artarken hangisi daha hizli duser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
