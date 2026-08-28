"""Alembic'in yerine konan tek koruma (ASAMA5_PLAN.md SS2): canli veritabanini
sqlalchemy.inspect ile yansitir, api/db/models.py'deki tablo/sutun adlarini
karsilastirir. Fark varsa duser. DB erisilemiyorsa pytest.skip (CI'da DB
olmayabilir) -- bu yuzden pytest disinda dogrudan calistirilmaz.

Calistirma:
    venv\\Scripts\\python.exe -m pytest tests/test_schema_sync.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.db.models import Base  # noqa: E402
from api.db.postgres import engine  # noqa: E402


def _live_inspector():
    try:
        insp = inspect(engine)
        insp.get_table_names()   # baglantiyi burada zorla dener
        return insp
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"veritabanina erisilemiyor: {exc}")


def test_all_model_tables_exist_in_db() -> None:
    insp = _live_inspector()
    db_tables = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        assert table.name in db_tables, f"tablo DB'de yok: {table.name}"


def test_all_model_columns_exist_in_db() -> None:
    insp = _live_inspector()
    for table in Base.metadata.tables.values():
        db_cols = {col["name"] for col in insp.get_columns(table.name)}
        model_cols = {col.name for col in table.columns}
        missing = model_cols - db_cols
        assert not missing, f"{table.name}: modelde olup DB'de olmayan sutunlar: {missing}"
