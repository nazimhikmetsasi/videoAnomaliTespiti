"""Tek MongoClient -- pymongo kendi baglanti havuzunu yonetir, istekler onu
paylasir (ASAMA5_PLAN.md SS4).

Istemci ILK KULLANIMDA kurulur, import aninda degil: MongoClient(url) URL'i
dogrular ve sifresiz bir URL'de ConfigurationError firlatir. Import aninda
kurulursa `api.workers.consumer` ortam degiskeni olmayan her yerde (ornegin
tests/test_consumer.py'nin brokersiz oz kontrolu) daha ice aktarilirken
patlar -- oysa test edilen sey saf bir fonksiyondur, Mongo'ya ihtiyaci yoktur.
"""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database

from api.config import MONGO_DB, MONGO_URL

_client: MongoClient | None = None


def get_mongo() -> Database:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL)
    return _client[MONGO_DB]
