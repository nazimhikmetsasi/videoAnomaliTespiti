"""Kafka producer: aday anomali olaylarini anomaly-candidates topic'ine basar.

WebSocket yayini bu dosyada YOK -- PLAN.md bu dosyayi "Kafka + WebSocket" diye
tarif eder ama WebSocket kismi Asama 6'dadir.

Goru dongusu Kafka yuzunden ASLA durmaz (docs/ASAMA4_PLAN.md SS2): produce()
kuyruga atip doner, teslim broker'a arka planda gerceklesir. Kuyruk doluysa
(BufferError) veya teslim basarisiz olursa hata sayilir ve son hata metni
raporlanir -- sessizce yutulmaz, ama goru hatti da hicbir zaman dusurulmez.
"""

from __future__ import annotations

import json

from confluent_kafka import Producer

from vision.rules.engine import Candidate
from vision.rules.postfall import FallOutcome

CANDIDATE_TOPIC = "anomaly-candidates"
OUTCOME_TOPIC = "fall-outcomes"
EOS_TYPE = "_EOS"
TICK_TYPE = "_TICK"      # nabiz: aday yokken de Spark su isaretini ilerletir
EOS_LEAD_SEC = 15.0      # akis sonu isaretcisi bu kadar ileri damgalanir (SS5.5)
SCHEMA_VERSION = 1


def _track_key(track_ids: list[int]) -> str:
    """Ayni iz hep ayni partition'a gitsin diye siralanmis, tireli anahtar."""
    return "-".join(str(t) for t in sorted(track_ids))


def tick_due(last_tick: float | None, now: float, tick_sec: float) -> bool:
    """Nabiz zamani geldi mi? tick_sec<=0 kapali; ilk cagri hemen nabiz atar."""
    return tick_sec > 0 and (last_tick is None or now - last_tick >= tick_sec)


def candidate_to_dict(cand: Candidate, camera_id: str, epoch_base: float) -> dict:
    """Candidate -> Kafka JSON govdesi (ASAMA4_PLAN.md SS4.1).

    event_time DUVAR saatidir (CameraPipeline.consume() atar): Spark su isareti
    butun kameralar icin ortaktir; sahne zamaniyla pencerelenirse yavas akan
    dosya kamerasinin adaylari "gec veri" diye atilir. Sure olcutleri (min_sec)
    yine sahne zamani `ts` ile hesaplanir. event_time yoksa (eval betikleri)
    eski davranis: epoch_base + ts.
    """
    # int()/float(): FeatureEngine/tracker degerleri numpy skalerdir
    # (float32/int64), json.dumps bunlari seri hale getiremez.
    return {
        "schema": SCHEMA_VERSION,
        "camera_id": camera_id,
        "anomaly_type": cand.anomaly_type,
        "track_key": _track_key(cand.track_ids),
        "track_ids": [int(t) for t in cand.track_ids],
        "score": float(cand.score),
        "idx": int(cand.idx),
        "ts": float(cand.ts),
        "event_time": (cand.event_time if cand.event_time is not None
                       else epoch_base + float(cand.ts)),
        "zone_name": cand.zone_name,
        "decided_by": cand.decided_by,
        "metrics": {k: float(v) for k, v in cand.metrics.items()},
        "thresholds_used": {k: float(v) for k, v in cand.thresholds_used.items()},
    }


def outcome_to_dict(o: FallOutcome, camera_id: str) -> dict:
    """FallOutcome -> fall-outcomes JSON govdesi (ASAMA13_4_PLAN.md SS3.2)."""
    return {
        "schema": SCHEMA_VERSION,
        "camera_id": camera_id,
        "track_id": int(o.track_id),
        "fall_time": None if o.fall_time is None else float(o.fall_time),
        "fall_ts": float(o.fall_ts),
        "outcome": o.outcome,
        "decided_ts": float(o.decided_ts),
        "adopted": [int(t) for t in o.adopted],
        "metrics": {k: float(v) for k, v in o.metrics.items()},
    }


class CandidatePublisher:
    """Aday olaylari Kafka'ya basar. Bloklamaz, hata firlatmaz."""

    def __init__(self, bootstrap: str, camera_id: str, *,
                 epoch_base: float = 0.0, topic: str = CANDIDATE_TOPIC,
                 queue_max: int = 100_000) -> None:
        self.camera_id = camera_id
        self.epoch_base = epoch_base
        self.topic = topic
        self.published = 0     # broker'a teslim edildigi onaylanan mesaj
        self.queued = 0        # produce() cagrisi kabul edilen mesaj
        self.failed = 0        # teslim edilemeyen + kuyruga alinamayan
        self.last_error = ""
        self.outcomes_skipped = 0   # fall_time'siz sonuc (eslesme imkansiz)
        self._last_event_time = epoch_base
        # acks=1: tek broker'li yerel kumede acks=all'in getirisi yok, sadece
        # gecikme ekler. linger.ms=50 + lz4: adaylar hacimli ve kisa omurlu;
        # kisa sure biriktirip sikistirmak tek tek basmaktan ucuz.
        self._producer = Producer({
            "bootstrap.servers": bootstrap,
            "linger.ms": 50,
            "compression.type": "lz4",
            "acks": 1,
            "queue.buffering.max.messages": queue_max,
        })

    def _delivery(self, err, _msg) -> None:
        if err is not None:
            self.failed += 1
            self.last_error = str(err)
        else:
            self.published += 1

    def _produce(self, body: dict, topic: str | None = None, key: str | None = None) -> None:
        # Anahtar mesajin KENDI camera_id/track_key'inden kurulur (self.camera_id
        # degil) -- _EOS'un camera_id'si "_eos"tur ve kendi partition setine gider.
        if key is None:
            key = f"{body['camera_id']}:{body['track_key']}"
        try:
            self._producer.produce(topic or self.topic, key=key.encode("utf-8"),
                                    value=json.dumps(body).encode("utf-8"),
                                    callback=self._delivery)
            self.queued += 1
        except BufferError as exc:
            self.failed += 1
            self.last_error = str(exc)

    def __call__(self, candidates: list[Candidate]) -> None:
        """Bloklamaz. Hata sayilir, yukari FIRLATILMAZ."""
        self._producer.poll(0)
        for cand in candidates:
            body = candidate_to_dict(cand, self.camera_id, self.epoch_base)
            self._last_event_time = max(self._last_event_time, body["event_time"])
            self._produce(body)

    def outcome(self, o: FallOutcome) -> None:
        """Dusme sonucu. fall_time yoksa olayla eslesemez: basilmaz, sayilir."""
        if o.fall_time is None:
            self.outcomes_skipped += 1
            return
        self._produce(outcome_to_dict(o, self.camera_id), OUTCOME_TOPIC,
                      f"{self.camera_id}:{o.track_id}")

    def tick(self, event_time: float) -> None:
        """Nabiz: aday olmasa da bu kameranin duvar saatini Spark'a iletir.
        Bloklamaz, hata firlatmaz (_produce hatayi sayar)."""
        self._last_event_time = max(self._last_event_time, event_time)
        self._produce({
            "schema": SCHEMA_VERSION,
            "camera_id": self.camera_id,
            "anomaly_type": TICK_TYPE,
            "track_key": "_tick",
            "track_ids": [],
            "score": 0.0,
            "idx": -1,
            "ts": 0.0,
            "event_time": event_time,
            "zone_name": None,
            "decided_by": "rule",
            "metrics": {},
            "thresholds_used": {},
        })

    def close(self, *, eos: bool = True, timeout: float = 10.0) -> None:
        """Akis sonu isaretcisini basar ve kuyrugu bosaltir.

        _EOS gerekli cunku Spark oturum penceresi damga (watermark) pencere
        sonunu gecince yazar; dosya klibi bitince akis durur, damga ilerlemez,
        klibin son olayi hic yazilmaz. _EOS damgayi ileri iter.
        """
        if eos:
            self._produce({
                "schema": SCHEMA_VERSION,
                "camera_id": "_eos",
                "anomaly_type": EOS_TYPE,
                "track_key": "_eos",
                "track_ids": [],
                "score": 0.0,
                "idx": -1,
                "ts": 0.0,
                "event_time": self._last_event_time + EOS_LEAD_SEC,
                "zone_name": None,
                "metrics": {},
                "thresholds_used": {},
            })
        self._producer.flush(timeout)
