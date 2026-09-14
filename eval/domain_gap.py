"""Alan farkinin KAYNAGINI olcer: model pilot kliplerde neden yaniliyor?

`docs/TEZ.md` SS4.2: holdout'ta kesinligi 0.81 olan model, 1080p/4K pilot
kliplerde 12 sahte FALL uretiyor. Bunun "cozunurluk farki" diye
aciklanmasi FAZLA KOLAY, cunku TCN'in girdisi zaten olcek-normalizedir:
iskelet koordinatlari bbox'a bolunur, hiz bbox yuksekligine bolunur.
Cozunurluk tek basina bu kanallari degistirmez.

Degismeyen tek sey KALMIYOR ama: 53 kanalin 17'si (34:51) HAM KEYPOINT
GUVENIDIR ve guven cozunurluge, poz kalitesine, kisinin karedeki
buyuklugune dogrudan baglidir. Egitim kumesi 320x240 gozetim kaydi,
pilot 1080p/4K. Model bu farki ogrenmis olabilir.

Bu betik iddia etmez, olcer: her kanal grubunun egitim ve pilot
dagilimlarini yan yana koyar.

    venv/Scripts/python.exe -m eval.domain_gap
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.tcn import CHANNELS, WINDOW  # noqa: E402

# frame_vector() yerlesimi (models/tcn.py):
GRUPLAR = {
    "iskelet x/y (bbox-normalize)": (0, 34),
    "keypoint guveni": (34, 51),
    "merkez hizi": (51, 53),
}


def egitim_pencereleri(root: Path) -> dict[str, np.ndarray]:
    """data/sequences/<SINIF>/*.npz -> sinif basina (N, WINDOW, CHANNELS)."""
    out: dict[str, np.ndarray] = {}
    for sinif_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        parcalar = []
        for npz in sorted(sinif_dir.glob("*.npz")):
            with np.load(npz) as veri:
                for anahtar in veri.files:
                    dizi = veri[anahtar]
                    if dizi.ndim == 3 and dizi.shape[1:] == (WINDOW, CHANNELS):
                        parcalar.append(dizi)
                    elif dizi.ndim == 2 and dizi.shape == (WINDOW, CHANNELS):
                        parcalar.append(dizi[None])
        if parcalar:
            out[sinif_dir.name] = np.concatenate(parcalar, axis=0)
    return out


def pilot_pencereleri(clips: list[Path], detector, stride: int = 25) -> np.ndarray:
    """Pilot klipleri gercek hattan gecirip pencere kurar.

    Pencere EGITIMDEKI ile ayni fonksiyondan gecer (`window_tensor` ->
    `frame_vector`); ayri bir kopya yazilsaydi olculen fark modelin gordugu
    fark olmazdi. `stride` egitimdeki kaydirmayla ayni (models/tcn.STRIDE).
    """
    from vision.rules.arbiter import window_tensor
    from vision.source import VideoSource
    from vision.stages.features import FeatureEngine
    from vision.stages.preprocess import Preprocessor
    from vision.stages.smoother import Smoother
    from vision.stages.tracker import Tracker

    parcalar: list[np.ndarray] = []
    for clip in clips:
        preprocess, smoother, features = Preprocessor(), Smoother(), FeatureEngine()
        tracker = Tracker(device=detector.device)
        sayac = 0
        with VideoSource(str(clip)) as source:
            while True:
                frame = source.read()
                if frame is None:
                    if source.eof.is_set():
                        break
                    continue
                image = preprocess(frame.image)
                ts = frame.idx / source.fps
                tracks = smoother(tracker.update(detector([image])[0], image), ts)
                pencereler = features(tracks, frame.idx, ts, image.shape[:2])
                sayac += 1
                if sayac % stride:
                    continue
                for pencere in pencereler.values():
                    tensor = window_tensor(pencere)
                    if tensor is not None:
                        parcalar.append(tensor)
        print(f"    {clip.name}: toplam {len(parcalar)} pencere")
    if not parcalar:
        return np.zeros((0, WINDOW, CHANNELS), dtype=np.float32)
    return np.stack(parcalar)


def ozet(ad: str, pencereler: np.ndarray) -> None:
    if pencereler.size == 0:
        print(f"  {ad:<28} pencere yok")
        return
    print(f"\n  {ad}  ({len(pencereler)} pencere)")
    print(f"    {'kanal grubu':<30} {'ortalama':>9} {'medyan':>9} "
          f"{'std':>9} {'p05':>9} {'p95':>9}")
    for etiket, (bas, bit) in GRUPLAR.items():
        dilim = pencereler[:, :, bas:bit].ravel()
        print(f"    {etiket:<30} {dilim.mean():9.3f} {np.median(dilim):9.3f} "
              f"{dilim.std():9.3f} {np.percentile(dilim, 5):9.3f} "
              f"{np.percentile(dilim, 95):9.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alan farkinin kaynagi")
    parser.add_argument("--sequences", default="data/sequences")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)

    egitim = egitim_pencereleri(Path(args.sequences))
    if not egitim:
        print("  egitim penceresi bulunamadi:", args.sequences)
        return 1

    print("=" * 70)
    print("  EGITIM KUMESI (320x240 gozetim kaydi)")
    print("=" * 70)
    hepsi = np.concatenate(list(egitim.values()), axis=0)
    ozet("TUM SINIFLAR", hepsi)
    for sinif, pencereler in sorted(egitim.items()):
        ozet(sinif, pencereler)

    clips = sorted(Path(args.clips).glob("*.mp4"))
    if not clips:
        print(f"\n  pilot klip yok: {args.clips}")
        return 0

    from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
    detector = PoseDetector(args.model or DEFAULT_WEIGHTS)
    pilot = pilot_pencereleri(clips, detector)

    print("\n" + "=" * 70)
    print(f"  PILOT KLIPLER (1080p/4K) -- {len(clips)} klip")
    print("=" * 70)
    ozet("PILOT", pilot)

    # Girdi dagilimlarindan sonra MODELIN CIKTISI: alan farki girdide
    # gorunmuyorsa, yanlis pozitifin kaynagi siniflandiricinin kendisidir.
    if pilot.size:
        from models.tcn import CLASSES, TCNClassifier
        try:
            clf = TCNClassifier()
        except Exception as exc:  # noqa: BLE001
            print(f"\n  siniflandirici yuklenemedi: {exc}")
        else:
            olasilik = clf(pilot)
            tahmin = olasilik.argmax(axis=1)
            print("\n  MODELIN PILOT PENCERELERDEKI TAHMINI")
            print(f"    {'sinif':<10} {'pencere':>8} {'oran':>7} "
                  f"{'ort. olasilik':>14} {'>=0.60':>8}")
            for i, ad in enumerate(CLASSES):
                secili = tahmin == i
                guclu = int(((tahmin == i) & (olasilik[:, i] >= 0.60)).sum())
                ort = float(olasilik[secili, i].mean()) if secili.any() else 0.0
                print(f"    {ad:<10} {int(secili.sum()):8d} "
                      f"{secili.mean() * 100:6.1f}% {ort:14.3f} {guclu:8d}")
            print("\n    Pilot klipler agirlikli olarak NORMAL davranis icerir;")
            print("    NORMAL disi her guclu tahmin yanlis pozitif adayidir.")

    if pilot.size and hepsi.size:
        print("\n  FARK (pilot - egitim), ortalama:")
        for etiket, (bas, bit) in GRUPLAR.items():
            e = hepsi[:, :, bas:bit].mean()
            p = pilot[:, :, bas:bit].mean()
            oran = (p - e) / abs(e) * 100 if e else float("nan")
            print(f"    {etiket:<30} {p - e:+9.3f}  ({oran:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
