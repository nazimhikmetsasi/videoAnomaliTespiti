"""Asama 9 egitim kliplerini `data/train/<SINIF>/` altina indirir.

Kaynaklar ve sinif eslemesi docs/ASAMA9_PLAN.md SS1'de gerekcesiyle yazili:

- SPHAR (github.com/AlexanderMelde/SPHAR-Dataset) — klipler depoya dogrudan
  islenmis, dosya dosya cekilir; 5.9 GB'lik depo klonlanmaz
- UR Fall Detection (fenix.ur.edu.pl) — 30 dusme + 40 gunluk etkinlik

    venv/Scripts/python.exe scripts/fetch_datasets.py --dry-run
    venv/Scripts/python.exe scripts/fetch_datasets.py --only FALL

Kaynak onekleri GERCEK dosya adlarindan dogrulandi (plan taslagindaki
tahminler yanlisti): `livevid` (lv degil), `utint` (ut degil), `uccrime`
(ucfcrime degil), havadan cekim `ucarg` / `ucaerial` / `okutama`.

Klasor listesi contents API'siyle DEGIL git trees API'siyle alinir: contents
sayfa basina 1000 ogede kesiliyor ve `walking` klasorunun 2800 klibinin
sonundaki virat kayitlari (NORMAL'in tek sabit kamera kaynagi) disarida
kaliyordu.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

import cv2

REPO = "AlexanderMelde/SPHAR-Dataset"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/master:videos/"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/master/videos/"
URFD_URL = "http://fenix.ur.edu.pl/~mkepski/ds/data/"
# URFD kare bazli etiket tasiyor: -1 ayakta, 0 gecis (dusme ani), 1 yerde.
# Dusme klibinin ~%40'i dusme ONCESI yuruyustur; bu dosya olmadan o kareler de
# FALL etiketi alir ve model yuruyusu dusme sanir (olculdu: FALL F1 0.333).
URFD_LABELS = ("urfall-cam0-falls.csv", "urfall-cam0-adls.csv")
LABELS_NAME = "_urfd_cam0_labels.csv"

# Kaynak secimi klipler GORULEREK yapildi (docs/ASAMA9_PLAN.md SS1, elle
# denetim). Elenenler ve gerekceleri:
#   okutama, ucaerial   drone / kus bakisi — govde acisi ve adim kaniti yok
#   ucarg _aerial_      ayni sebep; _rooftop_ da elendi, kisi ~30 piksel
#   virat               SPHAR bunlari anotasyon kutusuna kirpmis, klipler
#                       64x64-72x142 piksel; kisi cogunda hic gorunmuyor
#   uccrime             kesilmemis: medyan 92.7 sn, en uzun 538.7 sn. Olay
#                       birkac saniye, kalan her pencere yanlis etiketlenirdi
#   caviar, livevid     ayni sebep, kesilmemis (SPHAR "Known Caveats")
#   casia _jump_        RUN klasorunde ama eylem ziplama; RUN saf kalsin
SPHAR = {
    "FALL":   (("falling",), ("casia",), ()),
    "RUN":    (("running",), ("casia", "ucarg"), ("_jump_",)),
    "FIGHT":  (("hitting", "kicking"), ("bitint", "utint", "casia", "ucarg"), ()),
    "NORMAL": (("walking", "neutral"), ("casia", "bitint", "utint", "ucarg"), ()),
}
# Havadan / cati kamerasi her sinifta elenir (ucarg dosya adi kamerayi tasir).
REJECT = ("_aerial_", "_rooftop_")
CLASSES = tuple(SPHAR)
NORMAL_CAP = 600         # ham hali 4966 klip; diger uc sinifin toplami ~560
TIMEOUT = 60


def sphar_files(folder: str, prefixes: tuple[str, ...],
                reject: tuple[str, ...]) -> list[tuple[str, str, int]]:
    """(hedef ad, indirme adresi, bayt) — yalnizca kabul edilen oneklerdekiler."""
    with urllib.request.urlopen(TREE_URL + folder, timeout=TIMEOUT) as resp:
        tree = json.load(resp)["tree"]
    return [(item["path"], RAW_URL + folder + "/" + item["path"], item["size"])
            for item in tree
            if item["path"].startswith(prefixes)
            and not any(bad in item["path"] for bad in REJECT + reject)]


def urfd_files(kind: str, count: int) -> list[tuple[str, str, int]]:
    """kind: fall / adl. Boyut bilinmiyor (HEAD atmiyoruz), klip basi ~1.3 MB."""
    names = [f"{kind}-{i:02d}-cam0.mp4" for i in range(1, count + 1)]
    return [("urfd_" + n, URFD_URL + n, 1_300_000) for n in names]


def crop_right_half(path: Path) -> None:
    """URFD klipleri 640x240 yan yana: SOL derinlik haritasi, SAG renkli kare.

    Derinlik yarisindaki hayalet siluet YOLO'ya ikinci bir kisi gibi gorunur
    ve ayni olayi iki ize bolerdi. Kirpma indirme aninda bir kez yapilir,
    boylece dizi cikarimi normal bir videoyla calisir.
    """
    cap = cv2.VideoCapture(str(path))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if w < 2 * h:                # yan yana olmayan bir kaynak gelirse dokunma
        cap.release()
        return
    tmp = path.with_suffix(".tmp.mp4")
    writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w // 2, h))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(frame[:, w // 2:])
    cap.release()
    writer.release()
    tmp.replace(path)


def fetch_urfd_labels(root: Path) -> None:
    """Iki CSV'yi tek dosyada birlestirir: data/train/_urfd_cam0_labels.csv."""
    target = root / LABELS_NAME
    if target.exists() and target.stat().st_size > 0:
        return
    parts = []
    for name in URFD_LABELS:
        try:
            with urllib.request.urlopen(URFD_URL + name, timeout=TIMEOUT) as resp:
                parts.append(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            print(f"  [HATA] {name}: {exc}")
            return
    root.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(parts), encoding="utf-8")
    print(f"  URFD kare etiketleri: {target.name}")


def plan_class(name: str) -> list[tuple[str, str, int]]:
    folders, prefixes, reject = SPHAR[name]
    files: list[tuple[str, str, int]] = []
    for folder in folders:
        files.extend(sphar_files(folder, prefixes, reject))
    if name == "FALL":
        files.extend(urfd_files("fall", 30))
    if name == "NORMAL":
        files.extend(urfd_files("adl", 40))
        files = cap_by_source(files, NORMAL_CAP)
    return files


def cap_by_source(files: list[tuple[str, str, int]], cap: int) -> list[tuple[str, str, int]]:
    """Kaynak onegi basina esit pay, sabit tohum — yeniden calistirinca ayni kume."""
    buckets: dict[str, list] = {}
    for item in files:
        buckets.setdefault(item[0].split("_")[0], []).append(item)
    rng = random.Random(0)
    for group in buckets.values():
        rng.shuffle(group)
    picked: list[tuple[str, str, int]] = []
    while len(picked) < cap and any(buckets.values()):
        for group in buckets.values():
            if group and len(picked) < cap:
                picked.append(group.pop())
    return picked


def download(url: str, target: Path) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"  [HATA] {target.name}: {exc}")
        return False
    target.write_bytes(data)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Asama 9 egitim kliplerini indirir")
    parser.add_argument("--dry-run", action="store_true", help="indirme, yalniz tabloyu bas")
    parser.add_argument("--only", default="", help="virgullu sinif listesi, orn: FALL,RUN")
    parser.add_argument("--out", default="data/train", help="hedef dizin")
    args = parser.parse_args()

    wanted = [c.strip().upper() for c in args.only.split(",") if c.strip()] or list(CLASSES)
    bad = [c for c in wanted if c not in SPHAR]
    if bad:
        print(f"bilinmeyen sinif: {', '.join(bad)} (secenekler: {', '.join(CLASSES)})")
        return 2

    root = Path(__file__).resolve().parent.parent / args.out
    if not args.dry_run:
        fetch_urfd_labels(root)
    total_failed = 0
    print(f"{'sinif':8} {'klip':>6} {'MB':>9}  durum")
    for name in wanted:
        files = plan_class(name)
        size_mb = sum(s for _, _, s in files) / 1e6
        if args.dry_run:
            print(f"{name:8} {len(files):6d} {size_mb:9.1f}  (dry-run)")
            continue
        target_dir = root / name
        target_dir.mkdir(parents=True, exist_ok=True)
        got = skipped = failed = 0
        for filename, url, _ in files:
            path = target_dir / filename
            if path.exists() and path.stat().st_size > 0:
                # Kirpma bu betige sonradan eklendi: daha once inmis URFD
                # klipleri hala yan yana olabilir. crop_right_half kirpilmis
                # dosyada zaten hicbir sey yapmaz, atlama yolunda da cagrilir.
                if filename.startswith("urfd_"):
                    crop_right_half(path)
                skipped += 1
                continue
            if download(url, path):
                if filename.startswith("urfd_"):
                    crop_right_half(path)
                got += 1
            else:
                failed += 1
        total_failed += failed
        on_disk = sum(p.stat().st_size for p in target_dir.glob("*.mp4")) / 1e6
        print(f"{name:8} {len(files):6d} {on_disk:9.1f}  indi {got}  vardi {skipped}  hata {failed}")

    if total_failed:
        print(f"\n  {total_failed} dosya inmedi — betik yeniden calistirilabilir, "
              f"var olanlar atlanir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
