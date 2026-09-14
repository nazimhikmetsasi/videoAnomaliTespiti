"""Canli kaynakta uctan uca alarm gecikmesi: yeni olaylari akitir ve ozetler.

Neden yeni bir betik: gecikme `events` tablosundaki iki damgadan hesaplanir
ve EK OLCUM GEREKTIRMEZ --

    started_at : anomalinin BASLADIGI an (canli kaynakta gercek duvar saati;
                 vision/camera.py epoch_base = 0.0, aday ts'i zaten epoch)
    ended_at   : anomalinin bittigi an
    created_at : olay satirinin veritabanina YAZILDIGI an (PostgreSQL now())

Uc sayi raporlanir ve karistirilmamalari onemlidir:

    sure        = ended_at - started_at    anomalinin kendi suresi
    hat         = created_at - ended_at    ANOMALI BITTIKTEN sonra alarma
                                           kalan sure -- "tespit -> alarm"
    toplam      = created_at - started_at  ilk kanittan alarma

Operatorun ekraninda kirmizi alarmi goren yol `api/ws/alerts.py`'dir ve o da
ayni Kafka konusunu (`anomaly-events`) okur; yani WebSocket alarmi pratikte
`created_at` ile ayni ana denk gelir. Ayri bir WS damgasi tutulmamistir,
bu yuzden rapor "veritabanina yazim" der, "operatorun gozu" demez.

TASARIM TABANI: Spark oturum penceresi `spark_window_sec` (varsayilan 3 sn)
sessizlikten SONRA kapanir. Dolayisiyla `hat` suresi yapisal olarak
3 saniyenin altina inemez; olculen sayi bu tabanla birlikte okunmalidir.

    venv/Scripts/python.exe -m eval.latency_watch            # canli akit
    venv/Scripts/python.exe -m eval.latency_watch --report   # ozet tablo

Windows notu: onceki surumde bu is bir bash dongusunde `docker compose exec`
cagriliyordu; her turda yeni surec catallamak Git-Bash'in surec kaynagini
tuketti (`fork: Resource temporarily unavailable`). Burasi TEK surectir ve
veritabanina dogrudan baglanir.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

# Spark oturum penceresinin varsayilani; raporda taban olarak gosterilir.
DEFAULT_WINDOW_SEC = 3.0

# Sutunlar e. ile nitelenir: cameras tablosunda da `id` var, niteliksiz
# birakmak "column reference id is ambiguous" veriyor.
SELECT_COLS = """
    e.id, e.anomaly_type, e.decided_by, e.confidence,
    extract(epoch from (e.ended_at   - e.started_at)) AS sure,
    extract(epoch from (e.created_at - e.ended_at))   AS hat,
    extract(epoch from (e.created_at - e.started_at)) AS toplam,
    e.started_at
"""


def dsn() -> str:
    """docker-compose ana makineye 5433 yayinliyor (konteyner ici 5432)."""
    user = os.getenv("POSTGRES_USER", "anomaly")
    password = os.getenv("POSTGRES_PASSWORD", "")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "anomaly")
    return f"postgresql://{user}:{password}@localhost:{port}/{db}"


def load_env() -> None:
    """.env'i okur -- betik ana makinede calisiyor, Docker ortami yok."""
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def fetch_since(conn, last_id: int, camera: str | None) -> list[tuple]:
    where = "e.id > %s"
    params: list = [last_id]
    if camera:
        where += " AND c.name = %s"
        params.append(camera)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {SELECT_COLS} FROM events e "
                    f"JOIN cameras c ON c.id = e.camera_id "
                    f"WHERE {where} ORDER BY e.id", params)
        return cur.fetchall()


def max_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(max(id), 0) FROM events")
        return int(cur.fetchone()[0])


def _fmt(row) -> str:
    _id, tip, karar, conf, sure, hat, toplam, _ts = row
    return (f"  #{_id:<5} {tip:<15} {karar:<7} guven {float(conf):.2f}  "
            f"sure {sure:6.2f} sn   hat {hat:6.2f} sn   toplam {toplam:6.2f} sn")


def watch(camera: str | None, interval: float) -> int:
    load_env()
    with psycopg.connect(dsn()) as conn:
        conn.autocommit = True
        last = max_id(conn)
        print(f"  izleniyor (son olay #{last}); yeni olaylar asagi dusecek")
        print(f"  {'':7}{'tip':<15} {'karar':<7} {'':11}"
              f"{'anomali suresi':<14} {'hat':<13} toplam")
        try:
            while True:
                for row in fetch_since(conn, last, camera):
                    print(_fmt(row), flush=True)
                    last = max(last, row[0])
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n  durduruldu")
    return 0


def report(camera: str | None, since_id: int, window_sec: float) -> int:
    load_env()
    with psycopg.connect(dsn()) as conn:
        rows = fetch_since(conn, since_id, camera)
    if not rows:
        print("  olcum yok: bu id'den sonra olay uretilmemis")
        return 1

    print(f"\n  olay sayisi: {len(rows)}   (#{since_id} sonrasi"
          + (f", kamera {camera}" if camera else "") + ")\n")
    for row in rows:
        print(_fmt(row))

    hat = [float(r[5]) for r in rows]
    toplam = [float(r[6]) for r in rows]
    sure = [float(r[4]) for r in rows]

    def satir(ad: str, veri: list[float]) -> str:
        veri = sorted(veri)
        p95 = veri[min(len(veri) - 1, int(round(0.95 * (len(veri) - 1))))]
        return (f"  {ad:<28} {statistics.median(veri):7.2f} {min(veri):8.2f} "
                f"{max(veri):8.2f} {p95:8.2f}")

    print(f"\n  {'':28} {'medyan':>7} {'en dusuk':>8} {'en yuksek':>8} {'p95':>8}")
    print(satir("anomali suresi (sn)", sure))
    print(satir("tespit -> alarm (sn)", hat))
    print(satir("toplam, ilk kanittan (sn)", toplam))

    print(f"\n  Tasarim tabani: Spark oturum penceresi {window_sec:.0f} sn "
          f"sessizlikten SONRA kapanir;")
    print(f"  'tespit -> alarm' yapisal olarak bunun altina inemez.")
    print(f"  Olculen medyanin tabanin uzerindeki payi: "
          f"{statistics.median(hat) - window_sec:+.2f} sn")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="uctan uca alarm gecikmesi")
    parser.add_argument("--camera", default="", help="yalniz bu kamera adi")
    parser.add_argument("--interval", type=float, default=2.0, help="saniye")
    parser.add_argument("--report", action="store_true", help="ozet tablo bas")
    parser.add_argument("--since-id", type=int, default=0,
                        help="--report ile: bu olay id'sinden sonrasi")
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC)
    args = parser.parse_args(argv)

    camera = args.camera or None
    if args.report:
        return report(camera, args.since_id, args.window_sec)
    return watch(camera, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
