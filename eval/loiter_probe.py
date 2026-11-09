"""LOITERING neden tetiklenmiyor: kuralin gordugunu kare kare kaydeder.

Bulgu (docs/DURUM.md, 2026-09-14): `data/pilot/zone_01.mp4` 60.6 sn, insanlar
yasakli bolgede 10.8. saniyeden klip sonuna kadar duruyor, ZONE_VIOLATION 704
aday uretiyor ama LOITERING sifir. "Iz 30 sn yasamiyor" hipotezi curudu: en
uzun iz 32.5 sn. O olcum ilk-son gorulme ARALIGIYDI, kesintisiz sure degil.

Bu betik kuralin (vision/rules/loiter.py) sayaci sifirlayan IKI sartini ayri
ayri olcer, cunku hangisinin sorun oldugu cozumu degistirir:

  1. iz kopmasi   -- iz STALE_FRAMES (90) kareden uzun gorulmezse durum duser
  2. bolge disi   -- bolge modunda ayak TEK KARE bolge disina cikarsa
                     `still = False` ve sayac sifirlanir

Iz basina raporlanan:
  aralik           ilk-son gorulme (dunku olcum)
  kesintisiz iz    STALE_FRAMES'ten uzun bosluk olmadan gorulme
  kesintisiz bolge ayak noktasinin bolgede ARALIKSIZ kaldigi en uzun sure
                   -- kuralin gercekte biriktirdigi sey budur
  cikis sayisi     bolgeden cikis (sayac sifirlamasi) adedi
  en kisa cikis    bolge disinda kalinan en kisa sure; birkac karelik
                   cikislar ayak noktasi titremesidir, gercek cikis degil

    venv/Scripts/python.exe -m eval.loiter_probe
    venv/Scripts/python.exe -m eval.loiter_probe --clip data/pilot/zone_01.mp4
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.rules.engine import Thresholds  # noqa: E402
from vision.rules.loiter import STALE_FRAMES, LoiterRule  # noqa: E402


def kayit_topla(clip: Path, zones_path: str, model: str) -> tuple[dict, float, list]:
    """Iz basina [(idx, ts, bolgede_mi), ...] -- yalniz pozlu kareler, cunku
    kural motoru (engine.__call__) yalniz `has_pose` pencereleri gorur."""
    from vision.camera import load_zones
    from vision.source import VideoSource
    from vision.stages.features import FeatureEngine
    from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
    from vision.stages.preprocess import Preprocessor
    from vision.stages.smoother import Smoother
    from vision.stages.tracker import Tracker

    zones = load_zones(zones_path, clip.stem)
    kural = LoiterRule(zones)         # _matching_zone'u AYNEN kullanmak icin
    det = PoseDetector(model or DEFAULT_WEIGHTS)
    pre, sm, feats = Preprocessor(), Smoother(), FeatureEngine()
    tracker = Tracker(device=det.device)

    kayit: dict[int, list] = defaultdict(list)
    fps = 25.0
    with VideoSource(str(clip)) as src:
        fps = src.fps
        while True:
            frame = src.read()
            if frame is None:
                if src.eof.is_set():
                    break
                continue
            image = pre(frame.image)
            ts = frame.idx / src.fps
            tracks = sm(tracker.update(det([image])[0], image), ts)
            for tid, window in feats(tracks, frame.idx, ts, image.shape[:2]).items():
                last = window.last
                if not last.has_pose:
                    continue
                bolgede = (kural._matching_zone(last) is not None) if zones else None
                kayit[tid].append((last.idx, last.ts, bolgede))
    return kayit, fps, zones


def en_uzun_kosu(ornekler: list, fps: float, sart) -> tuple[float, list[float]]:
    """`sart` saglanan ardisik orneklerin en uzun suresi + kesilen bosluklar.
    Ornekler arasi bosluk STALE_FRAMES'i asarsa kosu da kopar (kuralla ayni)."""
    en_uzun, bas, onceki_idx = 0.0, None, None
    cikislar: list[float] = []
    cikis_bas = None
    for idx, ts, bolgede in ornekler:
        kopuk = onceki_idx is not None and idx - onceki_idx > STALE_FRAMES
        if kopuk:
            bas = None
        if sart(bolgede):
            if cikis_bas is not None:
                cikislar.append(ts - cikis_bas)
                cikis_bas = None
            if bas is None:
                bas = ts
            en_uzun = max(en_uzun, ts - bas)
        else:
            if bas is not None and cikis_bas is None:
                cikis_bas = ts
            bas = None
        onceki_idx = idx
    return en_uzun, cikislar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LOITERING sayac sifirlama olcumu")
    parser.add_argument("--clip", default="data/pilot/zone_01.mp4")
    parser.add_argument("--zones", default="eval/zones.json")
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)

    clip = Path(args.clip)
    kayit, fps, zones = kayit_topla(clip, args.zones, args.model)
    esik = Thresholds().loiter_sec

    print(f"\n  klip          : {clip.name}  ({fps:.0f} FPS)")
    print(f"  mod           : {'BOLGE (' + ', '.join(z.name for z in zones) + ')' if zones else 'CIPA'}")
    print(f"  esik          : {esik} sn,  iz kopma siniri {STALE_FRAMES} kare "
          f"({STALE_FRAMES / fps:.1f} sn)\n")
    print(f"  {'iz':>4} {'ornek':>6} {'aralik':>8} {'kesintisiz':>11} "
          f"{'kesintisiz':>11} {'cikis':>6} {'en kisa':>8}")
    print(f"  {'':>4} {'':>6} {'(sn)':>8} {'iz (sn)':>11} "
          f"{'bolge (sn)':>11} {'sayisi':>6} {'cikis sn':>8}")

    for tid in sorted(kayit, key=lambda t: -len(kayit[t])):
        ornek = kayit[tid]
        aralik = ornek[-1][1] - ornek[0][1]
        iz_sure, _ = en_uzun_kosu(ornek, fps, lambda b: True)
        if zones:
            bolge_sure, cikislar = en_uzun_kosu(ornek, fps, lambda b: bool(b))
            en_kisa = f"{min(cikislar):8.2f}" if cikislar else f"{'-':>8}"
            print(f"  {tid:4d} {len(ornek):6d} {aralik:8.1f} {iz_sure:11.1f} "
                  f"{bolge_sure:11.1f} {len(cikislar):6d} {en_kisa}")
        else:
            print(f"  {tid:4d} {len(ornek):6d} {aralik:8.1f} {iz_sure:11.1f} "
                  f"{'-':>11} {'-':>6} {'-':>8}")

    if zones:
        tum_cikis = [c for o in kayit.values() for c in en_uzun_kosu(o, fps, bool)[1]]
        if tum_cikis:
            kisa = sum(1 for c in tum_cikis if c <= 0.5)
            print(f"\n  bolge cikislari: {len(tum_cikis)}, bunlarin {kisa} tanesi "
                  f"<= 0.5 sn (ayak noktasi titremesi adayi)")
            print(f"  cikis sureleri : {', '.join(f'{c:.2f}' for c in sorted(tum_cikis))} sn")

        # Kisa cikislari affetseydik bolgede en uzun kalis ne olurdu?
        # Duzeltmenin BU klipte tetikleyip tetiklemeyecegini onceden soyler.
        print(f"\n  tolerans (sn)  en uzun bolgede kalis (sn)   esige ulasir mi")
        for tol in (0.0, 0.5, 1.0, 2.0, 3.0):
            en_iyi = max(toleransli_kalis(o, tol) for o in kayit.values())
            print(f"  {tol:12.1f}  {en_iyi:26.1f}   "
                  f"{'EVET' if en_iyi >= esik else 'hayir'}")
    return 0


def toleransli_kalis(ornekler: list, tolerans: float) -> float:
    """Bolge disinda `tolerans` saniyeden kisa kalinan bosluklari yok sayarak
    bolgede en uzun kalis. Iz kopmasi (STALE_FRAMES) yine kosuyu keser."""
    en_uzun, bas, disari, onceki_idx = 0.0, None, None, None
    for idx, ts, bolgede in ornekler:
        if onceki_idx is not None and idx - onceki_idx > STALE_FRAMES:
            bas, disari = None, None
        if bolgede:
            disari = None
            if bas is None:
                bas = ts
            en_uzun = max(en_uzun, ts - bas)
        else:
            if disari is None:
                disari = ts
            if ts - disari > tolerans:
                bas = None
        onceki_idx = idx
    return en_uzun


if __name__ == "__main__":
    raise SystemExit(main())
