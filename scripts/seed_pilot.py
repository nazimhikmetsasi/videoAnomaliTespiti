"""Pilot kliplerin veritabani karsiligini olusturur (ASAMA5_PLAN.md SS5).

data/pilot/*.mp4 icin bir 'cameras' satiri acar (name = klip adi, boylece
consumer'in `cameras WHERE id::text = :cid OR name = :cid` eslemesi klip
adiyla calisir), eval/zones.json'daki poligonlari ayni adli kameranin
'zones' satirlarina yazar. Tekrar calistirilabilir: var olan isim atlanir.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from api.db.models import Camera, Zone
from api.db.postgres import SessionLocal

ROOT = Path(__file__).resolve().parent.parent
PILOT_DIR = ROOT / "data" / "pilot"
ZONES_JSON = ROOT / "eval" / "zones.json"


def _ensure_camera(db, name: str, source: Path) -> Camera:
    cam = db.scalar(select(Camera).where(Camera.name == name))
    if cam is not None:
        print(f"kamera zaten var, atlaniyor: {name} (id={cam.id})")
        return cam
    cam = Camera(name=name, source=str(source), source_type="file")
    db.add(cam)
    db.flush()
    print(f"kamera olusturuldu: {name} (id={cam.id})")
    return cam


def _ensure_zones(db, cam: Camera, zone_defs: list[dict]) -> None:
    for zdef in zone_defs:
        existing = db.scalar(
            select(Zone).where(Zone.camera_id == cam.id, Zone.name == zdef["name"])
        )
        if existing is not None:
            print(f"  bolge zaten var, atlaniyor: {zdef['name']} (id={existing.id})")
            continue
        zone = Zone(
            camera_id=cam.id, name=zdef["name"], zone_type=zdef["zone_type"],
            polygon=zdef["polygon"], direction_vector=zdef.get("direction_vector"),
        )
        db.add(zone)
        db.flush()
        print(f"  bolge olusturuldu: {zdef['name']} (id={zone.id})")


def main() -> None:
    zones_by_camera = {
        k: v for k, v in json.loads(ZONES_JSON.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    clips = sorted(PILOT_DIR.glob("*.mp4"))
    if not clips:
        print(f"pilot klip bulunamadi: {PILOT_DIR}")
        return

    with SessionLocal() as db:
        for clip in clips:
            name = clip.stem
            cam = _ensure_camera(db, name, clip)
            if name in zones_by_camera:
                _ensure_zones(db, cam, zones_by_camera[name])
        db.commit()


if __name__ == "__main__":
    main()
