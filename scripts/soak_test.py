"""Asama 10.5: uzun kosu olcum kaydi. Hicbir sey BASLATMAZ, yalniz izler.

Kosuyu her zamanki gibi baslatirsin (`docker compose up -d` +
`scripts/run_pilot_cameras.py`); bu betik yanda calisir ve belirli araliklarla
TEK satir CSV yazar. Amac kosuyu bir daha tekrarlamadan tez tablosunu
uretebilmek: 8 saatlik bir olcumu hafizada tutmak yerine dosyaya yazmak.

Olculen sey FPS degil CURUMEdir: FPS ilk saat ile son saat arasinda dusuyor
mu, RAM/VRAM siziyor mu, dusen kare birikiyor mu, olay uretimi duruyor mu.
Bunlar dakikalik kosuda GORUNMEZ.

    venv/Scripts/python.exe scripts/soak_test.py
    venv/Scripts/python.exe scripts/soak_test.py --interval 60 --hours 8
    venv/Scripts/python.exe scripts/soak_test.py --report logs/soak.csv

`--report` hicbir sey olcmez, var olan CSV'den ozet tablo basar.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

# Windows konsolu cp1252; Turkce karakterli bir hata mesajini basmak
# UnicodeEncodeError atiyor ve HATA ISLEYICISI KOSUYU OLDURUYORDU
# (8 saatlik kosu 4. dakikada "baglanti iptal edildi" mesajinin g harfinde
# coktu). Basim asla catlamamali: kodlanamayan karakter yerine '?' gecsin.
sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "logs" / "soak.csv"
FIELDS = ("ts", "gecen_dk", "kamera", "fps_toplam", "fps_min", "dusen_toplam",
          "infer_ms_ort", "goru_rss_mb", "gpu_mb", "olay_sayisi", "storage_mb")


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {k.strip(): v.strip() for k, v in
            (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
             if "=" in line and not line.strip().startswith("#"))}


def login(base: str, password: str) -> str:
    # API OAuth2 form bekliyor, JSON degil.
    r = httpx.post(f"{base}/api/auth/login",
                   data={"username": "admin", "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def vision_rss_mb() -> float:
    """Goru surecinin (vision.run) toplam RSS'i. Bulunamazsa 0."""
    total = 0
    for proc in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or ())
            if "vision.run" in cmd:
                total += proc.info["memory_info"].rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total / 1e6


def gpu_mb() -> float:
    """nvidia-smi yoksa 0 -- olcum durmaz, sutun bos kalir."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10)
        return float(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 0.0


def dir_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def sample(base: str, headers: dict, storage: Path, started: float) -> dict:
    health = httpx.get(f"{base}/api/health/cameras", headers=headers, timeout=10).json()
    live = [c for c in health
            if c.get("age_sec") is not None and c["age_sec"] < 60]
    fps = [c.get("fps_actual") or 0.0 for c in live]
    infer = [c.get("infer_ms") or 0.0 for c in live]
    events = httpx.get(f"{base}/api/events?limit=1", headers=headers, timeout=10).json()
    return {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gecen_dk": round((time.time() - started) / 60, 1),
        "kamera": len(live),
        "fps_toplam": round(sum(fps), 1),
        "fps_min": round(min(fps), 1) if fps else 0.0,
        "dusen_toplam": sum(c.get("dropped") or 0 for c in live),
        "infer_ms_ort": round(statistics.mean(infer), 1) if infer else 0.0,
        "goru_rss_mb": round(vision_rss_mb(), 1),
        "gpu_mb": round(gpu_mb(), 1),
        "olay_sayisi": events.get("total", 0),
        "storage_mb": round(dir_mb(storage), 1),
    }


def report(csv_path: Path) -> int:
    """Var olan kayittan ilk saat / son saat karsilastirmasi."""
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if len(rows) < 2:
        print(f"  {csv_path}: ozet icin en az 2 satir gerek ({len(rows)} var)")
        return 1
    span = float(rows[-1]["gecen_dk"])
    first = [r for r in rows if float(r["gecen_dk"]) <= 60] or rows[:1]
    last = [r for r in rows if float(r["gecen_dk"]) >= span - 60] or rows[-1:]

    def avg(group, key):
        return statistics.mean(float(r[key]) for r in group)

    print(f"\n  kosu suresi          : {span / 60:.1f} saat  ({len(rows)} olcum)")
    print(f"  kamera               : {rows[-1]['kamera']}")
    print(f"\n  {'metrik':<22} {'ilk saat':>12} {'son saat':>12} {'degisim':>10}")
    for key, label in (("fps_toplam", "toplam FPS"), ("fps_min", "en dusuk kamera FPS"),
                       ("infer_ms_ort", "cikarim ms"), ("goru_rss_mb", "goru RSS MB"),
                       ("gpu_mb", "GPU MB"), ("storage_mb", "storage MB")):
        a, b = avg(first, key), avg(last, key)
        change = f"{(b - a) / a * 100:+.1f}%" if a else "-"
        print(f"  {label:<22} {a:12.1f} {b:12.1f} {change:>10}")
    print(f"\n  olay sayisi          : {rows[0]['olay_sayisi']} -> {rows[-1]['olay_sayisi']}")
    print(f"  dusen kare (toplam)  : {rows[-1]['dusen_toplam']}")
    print("\n  Not: canli kaynakta yuksek dusen kare NORMALDIR -- kamera ~30 FPS")
    print("  uretir, hat ~5 tuketir, gerisi tasarim geregi atilir.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Uzun kosu olcum kaydi")
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=60.0, help="saniye")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--storage", default=str(ROOT / "storage"))
    parser.add_argument("--report", default="", help="olcme, var olan CSV'yi ozetle")
    args = parser.parse_args()

    if args.report:
        return report(Path(args.report))

    password = load_env(ROOT / ".env").get("ADMIN_PASSWORD")
    if not password:
        print("  HATA: ADMIN_PASSWORD .env'de yok")
        return 1
    try:
        headers = {"Authorization": f"Bearer {login(args.base, password)}"}
    except httpx.HTTPError as exc:
        print(f"  HATA: giris basarisiz ({args.base}): {exc} -- yigin ayakta mi?")
        return 1

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.exists()
    started, deadline = time.time(), time.time() + args.hours * 3600
    print(f"  olcum: her {args.interval:.0f} sn, {args.hours} saat -> {csv_path}")
    print(f"  {'gecen':>7} {'kamera':>7} {'FPS':>7} {'RSS MB':>8} {'GPU MB':>8} {'olay':>7}")

    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        while time.time() < deadline:
            try:
                row = sample(args.base, headers, Path(args.storage), started)
            except httpx.HTTPError as exc:
                # Olcum kesintisi kosuyu DURDURMAZ; satir atlanir, sebep basilir.
                print(f"  [{time.strftime('%H:%M:%S')}] olcum alinamadi: {exc}")
                time.sleep(args.interval)
                continue
            writer.writerow(row)
            handle.flush()      # 8 saat sonra degil ANINDA diske; cokme olursa veri durur
            print(f"  {row['gecen_dk']:6.1f}d {row['kamera']:7} {row['fps_toplam']:7.1f} "
                  f"{row['goru_rss_mb']:8.1f} {row['gpu_mb']:8.1f} {row['olay_sayisi']:7}")
            time.sleep(args.interval)

    print(f"\n  bitti. ozet: python scripts/soak_test.py --report {csv_path}")
    return report(csv_path)


if __name__ == "__main__":
    sys.exit(main())
