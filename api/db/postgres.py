"""SQLAlchemy engine + oturum fabrikasi. Es zamanli (async degil) -- ucler
`def` ile yazilir, FastAPI otomatik is parcacigi havuzunda calistirir
(ASAMA5_PLAN.md SS4: 4 kameralik sistemde asyncpg'nin getirisi yok).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
