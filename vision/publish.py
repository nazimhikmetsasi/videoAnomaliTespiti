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

CANDIDATE_TOPIC = "anomaly-candidates"
EOS_TYPE = "_EOS"
EOS_LEAD_SEC = 15.0      # akis sonu isaretcisi bu kadar ileri damgalanir (SS5.5)
SCHEMA_VERSION = 1


def _track_key(track_ids: list[int]) -> str:
    """Ayni iz hep ayni partition'a gitsin diye siralanmis, tireli anahtar."""
    return "-".join(str(t) for t in sorted(track_ids))


def candidate_to_dict(cand: Candidate, camera_id: str, epoch_base: float) -> dict:
    """Candidate -> Kafka JSON govdesi (ASAMA4_PLAN.md SS4.1).

    event_time sahne zamanidir, duvar saati degildir: dosya kaynagi klibi
    kamera FPS'inden farkli hizda isleyebilir, duvar saatiyle pencerelenirse
    Spark penceresi olculemez sekilde kayar. Canli kaynakta epoch_base=0.0
    verilir, cand.ts zaten epoch oldugu icin iki mod ayni koda duser.
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
        "event_time": epoch_base + float(cand.ts),
        "zone_name": cand.zone_name,
        "decided_by": cand.decided_by,
        "metrics": {k: float(v) for k, v in cand.metrics.items()},
        "thresholds_used": {k: float(v) for k, v in cand.thresholds_used.items()},
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

    def _produce(self, body: dict) -> None:
        # Anahtar mesajin KENDI camera_id/track_key'inden kurulur (self.camera_id
        # degil) -- _EOS'un camera_id'si "_eos"tur ve kendi partition setine gider.
        key = f"{body['camera_id']}:{body['track_key']}"
        try:
            self._producer.produce(self.topic, key=key.encode("utf-8"),
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
