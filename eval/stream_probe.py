"""Spark akisinin olay kaybi deneyleri (docs/ASAMA13_PLAN.md, A1 ve A2).

Iki deney de veritabanina DOKUNMAZ: Kafka konulari dogrudan dinlenir,
Spark'in ne yazdigi `anomaly-events`'ten okunur. Asama 13.1'in duzeltmesi
AYNI deneylerle dogrulanir.

tek-dusme
    Sessiz sahnede tek bir dusme olayi Spark'tan ne zaman cikar? 3 FALL
    adayi basilir, sonra sessizlik. Kamera adi "probe_cam" veritabaninda
    yok; tuketici onu "bilinmeyen camera_id" diye atlar.

    Olcum (2026-11-10): 45 sn boyunca olay GELMEDI; ilgisiz tek bir aday
    basilinca 5.3 sn sonra geldi. Sebep: su isareti (watermark) yalniz yeni
    veri gelince ilerler.

    Cikis kodu: 0 = olay sessizlikte geldi, 1 = yalniz baska bir aday
    gelince geldi (A1 hatasi), 2 = hic gelmedi.

    13.1 sonrasi not: duzeltme su isaretini KAMERALARIN nabziyla ilerletir.
    "probe_cam" nabiz basmaz; dogrulama icin yaninda en az bir kamera nabiz
    basiyor olmalidir (kamera acik, --tick-sec 0 degil).

gelecek
    Gelecek tarihli ret (SPARK_FUTURE_SEC) calisiyor mu? probe_cam adina
    event_time = simdi + 3600 tek aday basilir, sonra tek-dusme akisi aynen
    kosar (yaninda nabiz basan kamera sart). Ret calismiyorsa su isareti bir
    saat ileri sicrar, dusme gec sayilir, olay gelmez. Cikis kodlari tek-dusme
    ile ayni: 0 = olay geldi (ret calisiyor), 1/2 = hata.

saat-kaymasi
    Coklu kamerada sahne saatleri ayrisinca adaylar su isaretinin altina
    dusup atiliyor mu? Yalniz DINLER; kameralar ayri bir terminalde ayni
    anda calistirilir:

    venv\\Scripts\\python.exe -m vision.run --source "data\\pilot\\fall_01.mp4,data\\pilot\\run_01.mp4,data\\pilot\\zone_01.mp4" --camera-id "fall_01,run_01,zone_01" --loop --rules --zones eval\\zones.json --no-reid --kafka localhost:9092 --max-frames 2400 --heartbeat-sec 0

    Olcum (2026-11-10, 4 dk): zone_01 (25 FPS) ortak saati surukledi;
    fall_01 adaylarinin %80'i, run_01'inkilerin %75'i su isaretinin altinda.

    "gec aday" ANLIK su isaretiyle hesaplanir (gorulen en buyuk event_time
    - 2 sn). Spark'in gercek su isareti bir mikro-yigin geriden gelir, bu
    yuzden sayi atilan aday icin UST SINIRDIR. Kesin kanit olay sutunudur
    ve 8 saatlik koşunun kendi verisidir (iki kamera 7 saat sifir olay).
    "geride" kameranin SON ADAYININ ortak saatin ne kadar gerisinde
    kaldigidir; kamera aday uretmedigi surece guncellenmez.

    Cikis kodu: 0 = gec aday yok, 1 = gec aday var (A2 hatasi).

    venv/Scripts/python.exe -m eval.stream_probe tek-dusme
    venv/Scripts/python.exe -m eval.stream_probe gelecek
    venv/Scripts/python.exe -m eval.stream_probe saat-kaymasi --sure 280
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from collections import defaultdict

from confluent_kafka import OFFSET_END, Consumer, Producer, TopicPartition

BOOT = "localhost:9092"
WATERMARK_SEC = 2.0     # stream/spark_job.py SPARK_WATERMARK_SEC varsayilani


def _consumer(topics: list[str]) -> Consumer:
    """Konularin SONUNDAN dinler: yalniz deney sirasinda gelen mesajlar."""
    cons = Consumer({"bootstrap.servers": BOOT, "group.id": f"probe-{uuid.uuid4()}",
                     "enable.auto.commit": False})
    atama = []
    for konu in topics:
        for p in cons.list_topics(konu, timeout=10).topics[konu].partitions:
            atama.append(TopicPartition(konu, p, OFFSET_END))
    cons.assign(atama)
    return cons


def _aday(tip: str, kamera: str, iz: str, event_time: float) -> dict:
    return {"schema": 1, "camera_id": kamera, "anomaly_type": tip, "track_key": iz,
            "track_ids": [int(iz)] if iz.isdigit() else [], "score": 0.9, "idx": 0,
            "ts": 0.0, "event_time": event_time, "zone_name": None, "decided_by": "rule",
            "metrics": {}, "thresholds_used": {}}


def tek_dusme(sessizlik: float, gelecek_sn: float = 0.0) -> int:
    kamera, iz = "probe_cam", "777"
    cons = _consumer(["anomaly-events"])
    cons.poll(1.0)          # atamanin oturmasi icin
    prod = Producer({"bootstrap.servers": BOOT})

    def bas(body: dict) -> None:
        prod.produce("anomaly-candidates",
                     key=f"{body['camera_id']}:{body['track_key']}".encode(),
                     value=json.dumps(body).encode())
        prod.flush(5)

    def bekle(sure: float) -> float | None:
        bas_t = time.time()
        while time.time() - bas_t < sure:
            msg = cons.poll(0.5)
            if msg is None or msg.error():
                continue
            if json.loads(msg.value()).get("camera_id") == kamera:
                return time.time() - bas_t
        return None

    if gelecek_sn:
        bas(_aday("FALL", kamera, iz, time.time() + gelecek_sn))
        print(f"  gelecek tarihli (+{gelecek_sn:.0f} sn) tek aday basildi", flush=True)
    t0 = time.time()
    for k in range(3):      # hits=3 >= spark_min_hits=2, FALL min_sec=0
        bas(_aday("FALL", kamera, iz, t0 + k * 0.1))
    print("  [0.0 sn] 3 FALL adayi basildi, sonra SESSIZLIK", flush=True)

    try:
        gecen = bekle(sessizlik)
        if gecen is not None:
            print(f"  olay {gecen:.1f} sn icinde geldi -- su isareti sessizlikte de ilerliyor")
            return 0
        print(f"  {sessizlik:.0f} sn boyunca olay GELMEDI", flush=True)
        tik = time.time()
        bas(_aday("_EOS", "_eos", "_eos", tik))
        print(f"  [{tik - t0:.1f} sn] tek bir ilgisiz aday basildi (event_time=simdi)", flush=True)
        gecen = bekle(30)
        if gecen is not None:
            print(f"  olay tikten {gecen:.1f} sn SONRA geldi "
                  f"(dusmeden {time.time() - t0:.1f} sn sonra)")
            print("  SONUC: sessiz sahnede olay, baska bir aday gelene kadar BEKLIYOR (A1)")
            return 1
        print("  tikten sonra da gelmedi -- baska bir sebep var")
        return 2
    finally:
        cons.close()


def _tablo(t0: float, ortak_max: float, son_et: dict, aday: dict, gec: dict,
           olay: dict) -> None:
    print(f"\n  t={time.time() - t0:5.0f} sn   ortak en buyuk event_time = "
          f"{ortak_max - t0:+.1f} sn (duvar saatine gore)", flush=True)
    print(f"    {'kamera':<10} {'geride (sn)':>12} {'aday':>7} {'gec aday':>9} {'olay':>6}",
          flush=True)
    for cam in sorted(son_et):
        print(f"    {cam:<10} {ortak_max - son_et[cam]:12.1f} {aday[cam]:7d} "
              f"{gec[cam]:9d} {olay[cam]:6d}", flush=True)


def saat_kaymasi(sure: float) -> int:
    cons = _consumer(["anomaly-candidates", "anomaly-events"])
    aday: dict[str, int] = defaultdict(int)
    olay: dict[str, int] = defaultdict(int)
    gec: dict[str, int] = defaultdict(int)
    son_et: dict[str, float] = {}
    ortak_max = 0.0

    t0 = time.time()
    sonraki = t0 + 30
    print(f"  dinleniyor ({sure:.0f} sn) -- kameralari ayri terminalde baslatin", flush=True)
    try:
        while time.time() - t0 < sure:
            msg = cons.poll(0.5)
            if msg is not None and not msg.error():
                try:
                    body = json.loads(msg.value())
                except ValueError:
                    body = {}
                cam = body.get("camera_id")
                if cam and not str(cam).startswith("_"):
                    if msg.topic() == "anomaly-candidates":
                        et = float(body.get("event_time", 0))
                        if ortak_max and et < ortak_max - WATERMARK_SEC:
                            gec[cam] += 1
                        aday[cam] += 1
                        son_et[cam] = max(son_et.get(cam, 0.0), et)
                        ortak_max = max(ortak_max, et)
                    else:
                        olay[cam] += 1
            if time.time() >= sonraki:
                sonraki += 30
                _tablo(t0, ortak_max, son_et, aday, gec, olay)
    finally:
        cons.close()

    _tablo(t0, ortak_max, son_et, aday, gec, olay)
    toplam_gec = sum(gec.values())
    print(f"\n  SONUC: {toplam_gec} gec aday"
          + (" -- adaylar su isaretinin altina dusuyor (A2)" if toplam_gec else ""))
    return 1 if toplam_gec else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spark akisi olay kaybi deneyleri")
    alt = parser.add_subparsers(dest="deney", required=True)
    p1 = alt.add_parser("tek-dusme", help="sessiz sahnede tek dusme (A1)")
    p1.add_argument("--sessizlik", type=float, default=45.0,
                    help="olayin kendiliginden gelmesi icin beklenen sure (sn)")
    p2 = alt.add_parser("saat-kaymasi", help="coklu kamerada saat kaymasi (A2)")
    p2.add_argument("--sure", type=float, default=280.0, help="dinleme suresi (sn)")
    p3 = alt.add_parser("gelecek", help="gelecek tarihli aday reddi")
    p3.add_argument("--sessizlik", type=float, default=45.0,
                    help="olayin kendiliginden gelmesi icin beklenen sure (sn)")
    args = parser.parse_args(argv)

    if args.deney == "tek-dusme":
        return tek_dusme(args.sessizlik)
    if args.deney == "gelecek":
        return tek_dusme(args.sessizlik, gelecek_sn=3600.0)
    return saat_kaymasi(args.sure)


if __name__ == "__main__":
    raise SystemExit(main())
