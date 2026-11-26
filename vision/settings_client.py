"""API'den kamera esiklerini periyodik ceker, calisan RuleEngine.thresholds'u
degistirir (ASAMA5_PLAN.md SS7). Pipeline yeniden baslamaz.

Sicak yuklemenin siniri: yalnizca kural esikleri (fall_tilt_deg, fall_norm_vy,
run_norm_speed, run_gait_speed, loiter_sec, fight_proximity) canli degisir.
pose_conf/track_conf/window_frames model/tracker/pencere kurulumunda donar --
API yaniti bunlari da tasisa da BURADA uygulanmaz, calisan Thresholds'taki
degerler korunur (bkz. dataclasses.replace kullanan _apply).

Asla istisna firlatmaz: ag hatasi, 401, bozuk/kismi JSON -- hepsinde son
bilinen esikler korunur, failures artar, hata metni saklanir.
"""

from __future__ import annotations

import dataclasses
import datetime
import threading
import time

import httpx
import numpy as np

from vision.rules.engine import RuleEngine, Zone

# Yalnizca bu alanlar canli degisir; geri kalani (pose_conf, track_conf,
# window_frames) yeniden baslatma ister (ASAMA5_PLAN.md SS7).
HOT_FIELDS = (
    "fall_tilt_deg", "fall_norm_vy", "run_norm_speed",
    "run_gait_speed", "loiter_sec", "fight_proximity",
)


def _parse_time(value) -> datetime.time | None:
    return datetime.time.fromisoformat(value) if value else None


def zones_from_api(items: list[dict], errors: list[str] | None = None) -> list[Zone]:
    """API bolge listesi -> Zone listesi. Pasif bolge atlanir; bozuk oge atlanir
    varsa `errors` listesine hata metni olarak eklenir (tek bozuk bolge
    otekileri dusurmez)."""
    zones: list[Zone] = []
    for item in items:
        try:
            if not item.get("is_active", True):
                continue
            vec = item.get("direction_vector")
            zones.append(Zone(
                name=item["name"],
                zone_type=item["zone_type"],
                polygon=np.array(item["polygon"], dtype=np.float32),
                active_from=_parse_time(item.get("active_from")),
                active_to=_parse_time(item.get("active_to")),
                direction_vector=tuple(float(v) for v in vec) if vec else None,
            ))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            if errors is not None:
                errors.append(f"bozuk bolge: {exc!r}")
    return zones


def _zones_signature(zones: list[Zone]) -> tuple:
    return tuple((z.name, z.zone_type, z.polygon.round(6).tolist(),
                  z.active_from, z.active_to, z.direction_vector) for z in zones)


class SettingsClient:
    def __init__(self, base_url: str, camera_id: str, engine: RuleEngine,
                 interval: float = 5.0, token: str | None = None) -> None:
        base = base_url.rstrip("/")
        self._url = f"{base}/api/settings/{camera_id}"
        self._zones_url = f"{base}/api/zones"
        self._camera_id = camera_id
        self._engine = engine
        self._interval = interval
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.applied = 0
        self.zones_applied = 0
        self._zones_sig: tuple | None = None
        self.failures = 0
        self.last_error = ""
        self.last_updated_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Arka plan daemon thread -- ana goru dongusunu bloklamaz."""
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(self._interval)

    def _poll_once(self) -> None:
        """Ag/HTTP katmani. Hicbir istisna disari sizmaz -- sayilir."""
        try:
            resp = httpx.get(self._url, headers=self._headers, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.failures += 1
            self.last_error = str(exc)
        else:
            self.apply(data)
        # Bolge yoklamasi ayri try: basarisizligi esik yoklamasini etkilemez.
        try:
            resp = httpx.get(self._zones_url, params={"camera_id": self._camera_id},
                             headers=self._headers, timeout=5.0)
            resp.raise_for_status()
            items = resp.json()
            if not isinstance(items, list):
                raise ValueError("bolge yaniti liste degil")
        except (httpx.HTTPError, ValueError) as exc:
            self.failures += 1
            self.last_error = str(exc)
            return
        self.apply_zones(items)

    def apply(self, data: dict) -> bool:
        """Ayri fonksiyon: brokersiz/agsiz test edilebilir (SS11). API
        yanitini calisan Thresholds'a uygular, degisiklik varsa True doner.

        `updated_at` degismediyse yeni nesne kurulmaz (gereksiz is yok).
        """
        updated_at = data.get("updated_at")
        if updated_at is None or updated_at == self.last_updated_at:
            return False
        try:
            updates = {field: data[field] for field in HOT_FIELDS}
            # dataclasses.replace: yeni bir Thresholds nesnesi kurar, HOT_FIELDS
            # disindaki (restart gerektiren) alanlar mevcut nesneden aynen
            # kopyalanir -- atomik atama, yari uygulanmis kume gorulemez (SS7).
            new_thresholds = dataclasses.replace(self._engine.thresholds, **updates)
        except (KeyError, TypeError) as exc:
            self.failures += 1
            self.last_error = f"bozuk/eksik yanit: {exc}"
            return False

        self._engine.thresholds = new_thresholds
        # tcn_min_conf Thresholds'ta degil hakemde yasar (kural esigi degil,
        # model guven kapisi). Hakem yoksa alan sessizce yok sayilir.
        if hasattr(self._engine, "min_conf") and "tcn_min_conf" in data:
            self._engine.min_conf = float(data["tcn_min_conf"])
        self.applied += 1
        self.last_updated_at = updated_at
        # Uygulama ani stdout'a yazilir: sicak yukleme gecikmesi (PUT ile bu
        # satir arasindaki sure) ancak boyle olculebilir (ASAMA5_PLAN.md SS12.3).
        print(f"  [{time.strftime('%H:%M:%S')}] esik guncellendi: "
              + ", ".join(f"{k}={updates[k]}" for k in HOT_FIELDS))
        return True

    def apply_zones(self, items: list[dict]) -> bool:
        """Bolgeler imzasi degistiyse motora uygulanir (bos liste gecerlidir)."""
        errors: list[str] = []
        zones = zones_from_api(items, errors)
        if errors:
            self.failures += len(errors)
            self.last_error = errors[-1]
        sig = _zones_signature(zones)
        if sig == self._zones_sig:
            return False
        self._engine.set_zones(zones)
        self._zones_sig = sig
        self.zones_applied += 1
        print(f"  [{time.strftime('%H:%M:%S')}] bolgeler guncellendi: {len(zones)} bolge")
        return True
