"""Tek ortam degiskeni okuma noktasi. 12 deger icin pydantic-settings gereksiz
(ASAMA5_PLAN.md SS1). DATABASE_URL/MONGO_URL ortamda varsa dogrudan kullanilir
(docker-compose api/consumer servisleri bunu verir); yoksa mevcut
POSTGRES_*/MONGO_* degiskenlerinden host'a gore kurulur (venv'den calisirken).
"""

from __future__ import annotations

import os


def _database_url() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    user = os.getenv("POSTGRES_USER", "anomaly")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "anomaly")
    port = os.getenv("POSTGRES_PORT", "5433")
    return f"postgresql+psycopg://{user}:{password}@localhost:{port}/{db}"


def _mongo_url() -> str:
    if url := os.getenv("MONGO_URL"):
        return url
    user = os.getenv("MONGO_USER", "anomaly")
    password = os.getenv("MONGO_PASSWORD", "")
    port = os.getenv("MONGO_PORT", "27018")
    return f"mongodb://{user}:{password}@localhost:{port}/"


DATABASE_URL = _database_url()
MONGO_URL = _mongo_url()
MONGO_DB = os.getenv("MONGO_DB", "anomaly")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))

API_PORT = int(os.getenv("API_PORT", "8000"))

# consumer.py (Asama 5, ikinci ajan) bunu kullanir; vision/ zaten kendi
# KAFKA_BOOTSTRAP_HOST'unu okur, burasi yalnizca api/ konteynerlerinedir.
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", os.getenv("KAFKA_BOOTSTRAP_INTERNAL", "localhost:9092"))

# Kanit dosyalarinin kok dizini (Asama 6). vision/ host'ta "storage" yazar,
# api konteynerinde ayni agac "/storage" salt-okunur baglanir (docker-compose.yml).
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

# api/llm.py (Asama 7). Bos anahtar = kanal kapali, ayri bir bayrak yok
# (ASAMA7_PLAN.md SS6).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "8.0"))
LLM_COOLDOWN_SEC = float(os.getenv("LLM_COOLDOWN_SEC", "600.0"))

# api/notify.py (Asama 7). Bos token/chat_id = kanal kapali (ASAMA7_PLAN.md SS6).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NOTIFY_MIN_INTERVAL_SEC = float(os.getenv("NOTIFY_MIN_INTERVAL_SEC", "1.0"))
