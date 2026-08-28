"""Tek MongoClient -- pymongo kendi baglanti havuzunu yonetir, istekler onu
paylasir (ASAMA5_PLAN.md SS4).

Istemci ILK KULLANIMDA kurulur, import aninda degil: MongoClient(url) URL'i
dogrular ve sifresiz bir URL'de ConfigurationError firlatir. Import aninda
kurulursa `api.workers.consumer` ortam degiskeni olmayan her yerde (ornegin
tests/test_consumer.py'nin brokersiz oz kontrolu) daha ice aktarilirken
patlar -- oysa test edilen sey saf bir fonksiyondur, Mongo'ya ihtiyaci yoktur.
"""

from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from api.config import MONGO_DB, MONGO_URL

_client: MongoClient | None = None


def get_mongo() -> Database:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL)
    return _client[MONGO_DB]


def link_pose_sequence(mongo: Database, mongo_ref: str | None, event_id: int) -> None:
    """pose_sequences.event_id'yi doldurur (ASAMA6_PLAN.md SS6, SS8.2).

    Eslesmenin IKI yonu de bunu cagirir -- yon 2 (consumer) pratikte baskin
    yoldur: kanit epizot kapanir kapanmaz gider, olay ise Spark gecikmesinden
    sonra dogar, yani kanit neredeyse her zaman once gelir.

    Hata yutulur: Postgres tarafinda olay ile kanit ZATEN baglanmistir, Mongo
    baglantisi yalnizca Asama 9'un TCN egitimi icin kolaylik saglar."""
    if not mongo_ref:
        return
    try:
        mongo.pose_sequences.update_one({"_id": ObjectId(mongo_ref)}, {"$set": {"event_id": event_id}})
    except (InvalidId, PyMongoError):
        pass
