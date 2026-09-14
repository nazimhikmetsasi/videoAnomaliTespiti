"""Kanit saklama politikasi: diski sinirlar, olay kaydini SILMEZ.

Olculen sorun (ASAMA10.5, docs/TEZ.md SS3.5): 4 kamerali kesintisiz kosuda
depo saatte 1.3 GB, gunde ~31 GB buyuyor. Sekiz saatlik kosu teknik onay
kriterini gecti ama sistem bu haliyle GUNLERCE calisamaz.

Iki kural birlikte isler, cunku tek basina ikisi de yetmez:

*   **Yas** ongorulebilir saklama verir ama diski sinirlamaz (yogun bir
    haftada 7 gun x 31 GB = 217 GB).
*   **Toplam boyut tavani** diski kesin sinirlar ama saklama suresini
    ongorulemez yapar (sakin bir hafta aylarca durur, yogun bir gun
    saatler icinde silinir).

Silinen sey yalniz DOSYADIR. `events` satiri, `clip_path` alani ve
Mongo'daki `pose_sequences` yerinde kalir: olay gecmisi ve olculen
metrikler bozulmaz. `GET /api/events/{id}/clip` bu durumda zaten "klip
dosyasi diskte yok" diyor -- `clip_path` hic yazilmamis olay icin donen
"klip bulunamadi"dan ayri bir mesaj, yani panel ikisini ayirt edebilir.

Kareler kliplerden UZUN yasar: depo icindeki paylari %3 (474 MB / 17 GB)
ve klip gidince panelde olayin tek gorsel izi onlar kalir. Varsayilan 90
gun, Mongo `pose_sequences` TTL indeksiyle ayni.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

# Varsayilanlar vision/run.py bayraklariyla ayni; burasi tek dogruluk kaynagi.
CLIP_DAYS = 7.0
FRAME_DAYS = 90.0
MAX_GB = 20.0

# Yalniz bu iki alt dizin ve bu iki uzanti silinebilir. Depo yolu disaridan
# (--storage-dir) geldigi icin genis bir silme yetkisi kaza riskidir.
PRUNABLE = {"clips": ".mp4", "frames": ".jpg"}


@dataclass
class PruneResult:
    deleted: int = 0
    freed_bytes: int = 0
    total_bytes_after: int = 0
    errors: int = 0

    @property
    def freed_mb(self) -> float:
        return self.freed_bytes / (1024 * 1024)

    @property
    def total_gb_after(self) -> float:
        return self.total_bytes_after / (1024 ** 3)


def _entries(storage_dir: Path) -> dict[str, list[tuple[Path, float, int]]]:
    """Alt dizin -> [(yol, mtime, boyut)]. Yas icin mtime kullanilir; dosya
    adindaki epoch damgasi da var ama mtime hem daha basit hem de elle
    kopyalanan/tasinmis dosyalarda dogru davranir."""
    found: dict[str, list[tuple[Path, float, int]]] = {}
    for sub, suffix in PRUNABLE.items():
        items: list[tuple[Path, float, int]] = []
        directory = storage_dir / sub
        if not directory.is_dir():
            found[sub] = items
            continue
        with os.scandir(directory) as it:
            for entry in it:
                if not entry.is_file() or not entry.name.endswith(suffix):
                    continue
                stat = entry.stat()
                items.append((Path(entry.path), stat.st_mtime, stat.st_size))
        items.sort(key=lambda row: row[1])          # en eski basta
        found[sub] = items
    return found


def _unlink(path: Path, result: PruneResult, size: int) -> bool:
    """Dosya artik diskte DEGILSE True -- cagiran bunu boyut hesabindan duser."""
    try:
        path.unlink()
    except FileNotFoundError:
        # Tarama ile silme arasinda kaybolmus. Istenen sonuc zaten olustu:
        # hata degil, ama BU kosunun sildigi de sayilmaz.
        return True
    except OSError:
        # Windows'ta yazim suren dosya kilitli olabilir; bir sonraki turda
        # silinir. Tek dosya hatasi budamayi DURDURMAZ.
        result.errors += 1
        return False
    result.deleted += 1
    result.freed_bytes += size
    return True


def prune(storage_dir: str | Path, *, clip_days: float = CLIP_DAYS,
          frame_days: float = FRAME_DAYS, max_gb: float = MAX_GB,
          now: float | None = None) -> PruneResult:
    """Once yasa gore, sonra gerekirse toplam boyuta gore budar.

    Boyut tavani asilirsa YALNIZ klipler silinir (en eskiden baslayarak):
    kareler deponun %3'u, hepsini silmek tavani kurtarmaz ama panelin tum
    gorsel gecmisini goturur.
    """
    storage_dir = Path(storage_dir)
    now = time.time() if now is None else now
    result = PruneResult()
    if not storage_dir.is_dir():
        return result

    found = _entries(storage_dir)
    limits = {"clips": clip_days, "frames": frame_days}
    survivors: dict[str, list[tuple[Path, float, int]]] = {}

    for sub, items in found.items():
        days = limits[sub]
        if days <= 0:                       # yas kurali kapali; boyut tavani kalir
            survivors[sub] = list(items)
            continue
        cutoff = now - days * 86400.0
        kept: list[tuple[Path, float, int]] = []
        for path, mtime, size in items:
            if mtime < cutoff and _unlink(path, result, size):
                continue
            kept.append((path, mtime, size))
        survivors[sub] = kept

    total = sum(size for items in survivors.values() for _, _, size in items)
    budget = int(max_gb * 1024 ** 3)
    if total > budget:
        for path, _, size in survivors["clips"]:
            if total <= budget:
                break
            if _unlink(path, result, size):
                total -= size

    result.total_bytes_after = total
    return result


class Retention:
    """Kanit yazicisinin her isten sonra cagirdigi kisitlayici.

    Budama kendisi ucuz degildir (7500 dosyalik `scandir` + `stat`), ama her
    olayda calistirmak da gereksiz. `min_interval` bunu saglar; ilk cagri
    hemen calisir ki uzun bir kosunun basinda devralinan eski dosyalar
    beklemeden temizlensin.

    **Tavan ANLIK degil ortalamadir.** Iki budama arasinda yazilan klipler
    tavanin uzerine cikar; asim en fazla `min_interval` kadarlik yazimdir.
    Olculen buyume hizi saatte 1.3 GB oldugundan 60 saniyede ~22 MB eder,
    yani 20 GB'lik tavanin binde biri. Kucuk tavanlarla (test) asim goreceli
    olarak buyuk gorunur -- olculdu: 10 MB tavanda canli kosu 20 MB'a kadar
    cikti, budama calisinca 9 MB'a indi.
    """

    def __init__(self, storage_dir: str | Path, *, clip_days: float = CLIP_DAYS,
                 frame_days: float = FRAME_DAYS, max_gb: float = MAX_GB,
                 min_interval: float = 60.0) -> None:
        self.storage_dir = storage_dir
        self.clip_days, self.frame_days, self.max_gb = clip_days, frame_days, max_gb
        self.min_interval = min_interval
        self._last_run: float | None = None      # None = hic kosmadi
        self.deleted = 0
        self.freed_bytes = 0
        self.last_total_gb = 0.0

    def maybe_prune(self, now: float | None = None) -> PruneResult | None:
        now = time.monotonic() if now is None else now
        if self._last_run is not None and now - self._last_run < self.min_interval:
            return None
        self._last_run = now
        result = prune(self.storage_dir, clip_days=self.clip_days,
                       frame_days=self.frame_days, max_gb=self.max_gb)
        self.deleted += result.deleted
        self.freed_bytes += result.freed_bytes
        self.last_total_gb = result.total_gb_after
        return result


def main() -> int:
    """Elle budama: `venv/Scripts/python.exe -m vision.retention --max-gb 20`."""
    import argparse

    parser = argparse.ArgumentParser(description="kanit deposunu buda")
    parser.add_argument("--storage-dir", default="storage")
    parser.add_argument("--clip-days", type=float, default=CLIP_DAYS)
    parser.add_argument("--frame-days", type=float, default=FRAME_DAYS)
    parser.add_argument("--max-gb", type=float, default=MAX_GB)
    parser.add_argument("--dry-run", action="store_true",
                        help="silme, yalniz ne silinecegini yaz")
    args = parser.parse_args()

    if args.dry_run:
        found = _entries(Path(args.storage_dir))
        now = time.time()
        total = sum(size for items in found.values() for _, _, size in items)
        print(f"  toplam: {total / 1024 ** 3:.1f} GB, tavan {args.max_gb} GB")

        kalan = total
        survivors: list[tuple[Path, float, int]] = []
        for sub, days in (("clips", args.clip_days), ("frames", args.frame_days)):
            cutoff = now - days * 86400.0
            old = [row for row in found[sub] if days > 0 and row[1] < cutoff]
            size = sum(row[2] for row in old)
            kalan -= size
            if sub == "clips":
                survivors = [row for row in found[sub] if row not in old]
            print(f"  {sub}: {len(found[sub])} dosya, {days:.0f} gunden eski "
                  f"{len(old)} dosya ({size / 1024 ** 3:.1f} GB)")

        # Yastan sonra tavan hala asiliyorsa en eski klipler de gider.
        budget = int(args.max_gb * 1024 ** 3)
        if kalan > budget:
            sayi, gider = 0, 0
            for _, _, size in survivors:
                if kalan - gider <= budget:
                    break
                sayi, gider = sayi + 1, gider + size
            print(f"  tavan asiliyor: en eski {sayi} klip daha silinir "
                  f"({gider / 1024 ** 3:.1f} GB)")
            kalan -= gider
        print(f"  budama sonrasi: {kalan / 1024 ** 3:.1f} GB")
        return 0

    result = prune(args.storage_dir, clip_days=args.clip_days,
                   frame_days=args.frame_days, max_gb=args.max_gb)
    print(f"  silinen: {result.deleted} dosya, {result.freed_mb:.0f} MB")
    print(f"  kalan  : {result.total_gb_after:.1f} GB")
    if result.errors:
        print(f"  silinemeyen (kilitli olabilir): {result.errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
