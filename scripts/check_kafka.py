"""Host -> localhost:9092 uctan uca Kafka dogrulamasi.

docs/DURUM.md'deki acik soruyu kapatir: host'ta calisan vision/ gercekten
localhost:9092'ye yazabiliyor mu. Benzersiz bir UUID'li _SELFTEST mesaji
anomaly-candidates'e basar, benzersiz group.id + auto.offset.reset=latest ile
geri okur ve gecikmeyi yazdirir. Kendi mesajini bulamazsa cikis kodu 1'dir.

Calistirma:
    venv\\Scripts\\python.exe scripts/check_kafka.py --bootstrap localhost:9092
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

from confluent_kafka import Consumer, Producer

TOPIC = "anomaly-candidates"
TIMEOUT_SEC = 15.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kafka uctan uca dogrulama")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--topic", default=TOPIC)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SEC)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = f"_SELFTEST:{uuid.uuid4()}"

    # earliest: "latest" ile abone-olma ve ilk-pozisyon-cozme arasinda yarisma
    # riski var (assignment() dogru donse bile ofset henuz cozulmemis olabilir).
    # Benzersiz group.id zaten yalnizca bu kosunun mesajlarini gormesini
    # sartlamiyor, o yuzden token karsilastirmasi tek basina yeterli kanit.
    consumer = Consumer({
        "bootstrap.servers": args.bootstrap,
        "group.id": f"check-kafka-{uuid.uuid4()}",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([args.topic])

    producer = Producer({"bootstrap.servers": args.bootstrap})
    sent_at = time.monotonic()
    producer.produce(args.topic, key=b"_selftest", value=token.encode("utf-8"))
    flush_pending = producer.flush(args.timeout)
    if flush_pending:
        print(f"  HATA: {flush_pending} mesaj teslim edilemedi ({args.bootstrap})")
        consumer.close()
        return 1

    deadline = time.monotonic() + args.timeout
    found = False
    recv_at = 0.0
    while time.monotonic() < deadline:
        msg = consumer.poll(0.5)
        if msg is None or msg.error():
            continue
        if msg.value() and msg.value().decode("utf-8", "ignore") == token:
            found = True
            recv_at = time.monotonic()
            break
    consumer.close()

    if not found:
        print(f"  HATA: {args.timeout:.0f} sn icinde kendi mesajimi geri okuyamadim "
              f"({args.bootstrap} -> {args.topic}). Host, Kafka'ya yazabiliyor ama "
              f"kendi yazdigini okuyamiyor olabilir -- port/ag yapilandirmasini kontrol et.")
        return 1

    print(f"  OK: host -> {args.bootstrap} -> {args.topic} uctan uca calisiyor. "
          f"gecikme: {(recv_at - sent_at) * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
