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
import threading
import time

import httpx

from vision.rules.engine import RuleEngine

# Yalnizca bu alanlar canli degisir; geri kalani (pose_conf, track_conf,
# window_frames) yeniden baslatma ister (ASAMA5_PLAN.md SS7).
HOT_FIELDS = (
    "fall_tilt_deg", "fall_norm_vy", "run_norm_speed",
    "run_gait_speed", "loiter_sec", "fight_proximity",
)


class SettingsClient:
    def __init__(self, base_url: str, camera_id: str, engine: RuleEngine,
                 interval: float = 5.0, token: str | None = None) -> None:
        self._url = f"{base_url.rstrip('/')}/api/settings/{camera_id}"
        self._engine = engine
        self._interval = interval
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.applied = 0
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
            return
        self.apply(data)

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
        self.applied += 1
        self.last_updated_at = updated_at
        # Uygulama ani stdout'a yazilir: sicak yukleme gecikmesi (PUT ile bu
        # satir arasindaki sure) ancak boyle olculebilir (ASAMA5_PLAN.md SS12.3).
        print(f"  [{time.strftime('%H:%M:%S')}] esik guncellendi: "
              + ", ".join(f"{k}={updates[k]}" for k in HOT_FIELDS))
        return True
