"""Kafka tuketici: anomaly-events -> PostgreSQL events + MongoDB telemetry.

Goru hattinin publish.py'si gibi bu da ASLA tek bozuk mesajdan durmaz (SS6.6):
JSON/alan hatasinda mesaj atlanir (offset commit edilir), veritabani
hatasinda ise commit edilmez, ustel geri cekilmeyle AYNI mesaj yeniden
denenir -- gecici baglanti kopmasi olay kaybina yol acmamali.

event_to_row SAF fonksiyondur (DB'ye dokunmaz), tests/test_consumer.py
brokersiz onu dogrudan cagirir (ASAMA5_PLAN.md SS6.2).
"""

from __future__ import annotations

import datetime
import json
import signal
import threading

from confluent_kafka import Consumer
from pymongo.errors import PyMongoError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from api.config import KAFKA_BOOTSTRAP
from api.db.models import Event
from api.db.mongo import get_mongo
from api.db.postgres import SessionLocal

TOPIC = "anomaly-events"
GROUP_ID = "anomaly-event-consumer"

# SS6.3: skorlar tipler arasi karsilastirilabilir degil, kademelendirme yok.
# Bilinmeyen tip (henuz CHECK kisitina eklenmemis yeni bir kural) "medium"
# alir -- INSERT bu durumda events.anomaly_type CHECK'inde patlarsa SS6.6
# geregi db_error olarak yeniden denenir, sema (init.sql) guncellenince gecer.
SEVERITY = {
    "FALL": "critical", "FIGHT": "critical",
    "ZONE_VIOLATION": "high", "RUN_ZONE": "high",
    "RUN": "medium", "WRONG_DIRECTION": "medium",
    "LOITERING": "low",
}


def event_to_row(msg: dict, camera_id: int, zone_id: int | None) -> dict | None:
    """Kafka govdesi -> events satiri. DB'ye dokunmaz (SS6.2). Zorunlu alan
    eksik/bozuksa None doner, istisna firlatmaz."""
    try:
        anomaly_type = msg["anomaly_type"]
        confidence = min(max(float(msg["score"]), 0.0), 0.999)  # sutun NUMERIC(4,3)
        started_at = datetime.datetime.fromtimestamp(float(msg["start_time"]), tz=datetime.timezone.utc)
        ended_at = datetime.datetime.fromtimestamp(float(msg["end_time"]), tz=datetime.timezone.utc)
        duration_ms = round(float(msg["duration_sec"]) * 1000)
        track_ids = [int(t) for t in msg["track_ids"]]
    except (KeyError, TypeError, ValueError):
        return None

    return {
        "camera_id": camera_id,
        "zone_id": zone_id,
        "anomaly_type": anomaly_type,
        "track_ids": track_ids,
        "confidence": confidence,
        "severity": SEVERITY.get(anomaly_type, "medium"),
        "decided_by": "rule",           # TCN Asama 9'da gelir
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "frame_path": None, "clip_path": None,
        "llm_report_tr": None, "mongo_ref": None,
        "status": "new",
    }


class CameraCache:
    """camera_id metni -> DB int id (SS5). Kayipta bir kez tazelenir; yeni
    kamera eklenmisse bir sonraki cagrida bulunur, yoksa mesaj atlanir."""

    def __init__(self) -> None:
        self._map: dict[str, int] = {}

    def resolve(self, db: Session, raw_cid: str) -> int | None:
        if raw_cid in self._map:
            return self._map[raw_cid]
        self._reload(db)
        return self._map.get(raw_cid)

    def _reload(self, db: Session) -> None:
        self._map.clear()
        for cid, name in db.execute(text("SELECT id, name FROM cameras")).all():
            self._map[str(cid)] = cid
            self._map[name] = cid


class ZoneCache:
    """(camera_id, zone_name) -> zone_id. Bulunamazsa None -- kozmetik bir
    bag oldugu icin kayip normal bir durumdur, tazeleme gerekmez (SS5)."""

    def __init__(self) -> None:
        self._map: dict[tuple[int, str], int] = {}
        self._loaded = False

    def resolve(self, db: Session, camera_id: int, zone_name: str | None) -> int | None:
        if not zone_name:
            return None
        if not self._loaded:
            for zid, cid, name in db.execute(text("SELECT id, camera_id, name FROM zones")).all():
                self._map[(cid, name)] = zid
            self._loaded = True
        return self._map.get((camera_id, zone_name))


def _insert_event(db: Session, row: dict) -> int | None:
    """ON CONFLICT DO NOTHING RETURNING id -- idx_events_dedup dortlusunu
    kullanir (SS6.4). Donen id yoksa mesaj zaten islenmis demektir."""
    stmt = (
        pg_insert(Event.__table__)
        .values(**row)
        .on_conflict_do_nothing(
            index_elements=["camera_id", "anomaly_type", "started_at", "track_ids"])
        .returning(Event.__table__.c.id)
    )
    return db.execute(stmt).scalar()


class PermanentInsertError(Exception):
    """Yeniden denemenin duzeltemeyecegi INSERT hatasi (CHECK/FK ihlali)."""


def _insert_with_retry(row: dict, stop) -> int | None:
    """Veritabani hatasinda commit edilmez, ustel geri cekilmeyle AYNI satir
    yeniden denenir (SS6.6). Kapanis istendiyse (stop set) vazgecer.

    IntegrityError AYRIDIR: tekrar kaydi zaten ON CONFLICT ile eleniyor, geriye
    kalan butunluk hatasi CHECK/FK ihlalidir (ornegin sema henuz tanimadigi bir
    anomaly_type). Bunu yeniden denemek tuketiciyi sonsuz donguye sokar ve
    ARKASINDAKI TUM olaylari bloklar; mesaj bozuk sayilip atlanir."""
    delay = 1.0
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                new_id = _insert_event(db, row)
                db.commit()
                return new_id
        except IntegrityError as exc:
            raise PermanentInsertError(str(exc.orig)) from exc
        except SQLAlchemyError as exc:
            print(f"  DB hatasi, {delay:.0f} sn sonra yeniden denenecek: {exc}")
            stop.wait(delay)
            delay = min(delay * 2, 30.0)
    return None


def _write_telemetry(event_id: int, camera_id: int, msg: dict) -> None:
    """MongoDB telemetry belgesi (SS6.5). Hata firlarsa sayilir, tuketici
    durmaz -- Postgres satiri zaten yazildi, kaynak gercek orasidir."""
    track_ids = msg.get("track_ids") or []
    doc = {
        "camera_id": camera_id,
        "track_id": track_ids[0] if track_ids else None,
        "event_id": event_id,
        "window_start": msg.get("start_ts"),
        "window_end": msg.get("end_ts"),
        "metrics": msg.get("metrics", {}),
        "hits": msg.get("hits"),
        "rule_verdict": {
            "type": msg.get("anomaly_type"),
            "score": msg.get("score"),
            "thresholds_used": msg.get("thresholds_used", {}),
        },
        "model_verdict": None,
        "arbiter": "rule",
        "spark_verdict": "confirmed",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    get_mongo()["telemetry"].insert_one(doc)


def run() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",   # tuketici Spark'tan sonra kalkabilir
        "enable.auto.commit": False,       # SS6.4: offset DB yazimindan sonra elle
    })
    consumer.subscribe([TOPIC])

    cameras, zones = CameraCache(), ZoneCache()
    counters = {"processed": 0, "duplicates": 0, "malformed": 0,
                "skipped_unknown_camera": 0, "mongo_errors": 0}
    print(f"  tuketici basladi: {KAFKA_BOOTSTRAP} -> {TOPIC} (group={GROUP_ID})")

    try:
        while not stop.is_set():
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"  kafka hata: {msg.error()}")
                continue
            try:
                body = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                counters["malformed"] += 1
                consumer.commit(msg)
                continue

            with SessionLocal() as db:
                camera_id = cameras.resolve(db, str(body.get("camera_id")))
                if camera_id is None:
                    counters["skipped_unknown_camera"] += 1
                    print(f"  bilinmeyen camera_id, atlaniyor: {body.get('camera_id')!r}")
                    consumer.commit(msg)
                    continue
                zone_id = zones.resolve(db, camera_id, body.get("zone_name"))

            row = event_to_row(body, camera_id, zone_id)
            if row is None:
                counters["malformed"] += 1
                consumer.commit(msg)
                continue

            try:
                new_id = _insert_with_retry(row, stop)
            except PermanentInsertError as exc:
                counters["malformed"] += 1
                print(f"  satir reddedildi (kalici hata), atlaniyor: {exc}")
                consumer.commit(msg)
                continue
            if stop.is_set() and new_id is None:
                break   # kapanis istendi, bu mesaj offset commit edilmeden birakilir
            if new_id is None:
                counters["duplicates"] += 1
            else:
                counters["processed"] += 1
                try:
                    _write_telemetry(new_id, camera_id, body)
                except PyMongoError as exc:
                    counters["mongo_errors"] += 1
                    print(f"  mongo yazim hatasi (event {new_id}): {exc}")
            consumer.commit(msg)
    finally:
        consumer.close()
        print(f"  tuketici kapandi -- islenen {counters['processed']}  "
              f"tekrar {counters['duplicates']}  bozuk {counters['malformed']}  "
              f"bilinmeyen-kamera {counters['skipped_unknown_camera']}  "
              f"mongo-hata {counters['mongo_errors']}")


if __name__ == "__main__":
    run()
