"""Asama 13.5 Paket A: yon bolgesi dogrulamasi, kamera adiyla bolge listesi,
Spark min_sec varsayilanlari, panel yon cizimi.

Veritabani gerektirenler Postgres'e erisilemezse skip eder.

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_5_bolge.py -q
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.schemas import ZoneIn  # noqa: E402
from stream.filters import MIN_SEC_DEFAULT_MAP  # noqa: E402

_POLY = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]


def _zone(**over) -> dict:
    base = {"camera_id": 1, "name": "yon", "zone_type": "direction",
            "polygon": _POLY, "direction_vector": [1.0, 0.0]}
    base.update(over)
    return base


# ------------------------------------------------------------------ ZoneIn
def test_zonein_accepts_valid_vector() -> None:
    assert ZoneIn(**_zone()).direction_vector == [1.0, 0.0]


@pytest.mark.parametrize("vec", [[0.0, 0.0], [1e-9, 0.0], [1.0, 0.0, 0.0], [1.0],
                                 [float("nan"), 0.0], [float("inf"), 1.0]])
def test_zonein_rejects_bad_vector(vec) -> None:
    with pytest.raises(ValidationError) as ei:
        ZoneIn(**_zone(direction_vector=vec))
    assert "direction_vector [dx, dy] olmali" in str(ei.value)


# ------------------------------------------------------------ list_zones (DB)
@pytest.fixture()
def db():
    from sqlalchemy import text

    from api.db.postgres import SessionLocal
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        session.close()
        pytest.skip(f"veritabanina erisilemiyor: {exc}")
    try:
        yield session
    finally:
        session.rollback()  # test verisi hic commit edilmez
        session.close()


def test_list_zones_by_name_id_and_unknown(db) -> None:
    from api.db.models import Camera, Zone
    from api.routers.zones import list_zones

    name = "t135_" + uuid.uuid4().hex[:8]
    cam = Camera(name=name, source="x", source_type="file")
    db.add(cam)
    db.flush()
    db.add(Zone(camera_id=cam.id, name="z", zone_type="direction", polygon=_POLY,
                direction_vector=[1.0, 0.0], is_active=True))
    db.flush()
    by_name = list_zones(camera_id=name, db=db, _={})
    by_id = list_zones(camera_id=str(cam.id), db=db, _={})
    assert [z.name for z in by_name] == ["z"] == [z.name for z in by_id]
    # Bilinmeyen kamera 404: bos liste vision'a "bolge yok" der, dosyadakileri silerdi.
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        list_zones(camera_id="yok_" + uuid.uuid4().hex, db=db, _={})
    assert exc_info.value.status_code == 404


# --------------------------------------------------------------- min_sec map
def test_min_sec_map_has_new_keys_matching_init_sql() -> None:
    assert MIN_SEC_DEFAULT_MAP["RUN_ZONE"] == 1.0
    assert MIN_SEC_DEFAULT_MAP["WRONG_DIRECTION"] == 1.0
    sql = (ROOT / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8")
    m = re.search(r"spark_min_sec\s+JSONB\s+NOT NULL DEFAULT\s*'(\{.*?\})'", sql, re.S)
    assert m, "init.sql spark_min_sec varsayilani bulunamadi"
    assert json.loads(m.group(1)) == MIN_SEC_DEFAULT_MAP


# ------------------------------------------------------------------- panel
def _code() -> str:
    src = (ROOT / "frontend" / "js" / "bolgeler.js").read_text(encoding="utf-8")
    return "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("//"))


def test_bolgeler_direction_option_and_required_vector() -> None:
    code = _code()
    assert '<option value="direction">Yön (ters yön)</option>' in code
    assert re.search(r'zoneType === "direction" && !draftVector', code)  # vektorsuz kayit yok
    assert 'direction_vector: zoneType === "direction" ? draftVector : null' in code
    assert "marker-end" in code
    assert code.count('id="dirArrowHead"') == 1  # marker tek yerde tanimli
