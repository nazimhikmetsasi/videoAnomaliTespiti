"""Telegram bildirimi: kuyruk + tek worker thread (ASAMA7_PLAN.md SS4).

Neden ayri is parcacigi: consumer.py'nin ana donguse SENKRONDUR ve offset
commit etmeden once bekler; 3-8 sn'lik bir Gemini + Telegram turu arkadaki
olaylarin veritabanina yazilmasini geciktirir. enqueue() bu yuzden mikro-
saniyeler icinde doner, gercek is bu dosyadaki worker thread'de olur:

    consumer dongusu --enqueue(event_id)--> Queue --> worker thread
       (bloklanmaz, us)                               LLM + Telegram

Kirmizi alarm zaten api/ws/alerts.py'den AYRI bir process olarak yayinlandigi
icin bu dosyanin gecikmesi operatorun ekranini hicbir kosulda geciktirmez.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import httpx
from sqlalchemy import text

from api.config import NOTIFY_MIN_INTERVAL_SEC, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from api.db.models import Notification
from api.db.postgres import SessionLocal
from api.llm import generate_report
from api.storage_paths import storage_path

_queue: queue.Queue[int | None] = queue.Queue(maxsize=200)
_thread: threading.Thread | None = None

# testler MockTransport ile degistirir (SS8); None -- gercek agda varsayilan
# httpx tasiyicisi kullanilir.
_transport: httpx.BaseTransport | None = None
# testler yamalar (SS8 madde 3): gercek time.sleep hicbir testte cagrilmaz.
_sleep = time.sleep

_TIMEOUT_SEC = 10.0
_CAPTION_LIMIT = 1000

_counters = {"sent": 0, "failed": 0, "dropped": 0, "llm": 0, "template": 0,
             "skipped": 0}


def enqueue(event_id: int) -> None:
    """consumer.py'nin cagirdigi TEK fonksiyon (SS4.5). Kuyruk dolarsa EN
    ESKI oge dusurulur: kirmizi alarm zaten WebSocket'ten operatore gitti,
    burada kaybolan yalnizca telefon bildirimidir ve eski bir bildirim
    yenisinden degersizdir."""
    try:
        _queue.put_nowait(event_id)
    except queue.Full:
        try:
            _queue.get_nowait()
            _counters["dropped"] += 1
        except queue.Empty:
            pass
        try:
            _queue.put_nowait(event_id)
        except queue.Full:
            pass


def _truncate_caption(text_: str) -> str:
    """Telegram caption siniri 1024 karakter -- SS4.2 geregi 1000'de kirpilir."""
    return text_ if len(text_) <= _CAPTION_LIMIT else text_[:_CAPTION_LIMIT] + "…"


def _resolve_photo_path(frame_path: str | None) -> Path | None:
    if not frame_path:
        return None
    path = storage_path(frame_path)
    if path is None or not path.is_file():
        return None
    return path


def _do_request(chat_id: str, text_: str, photo_path: Path | None) -> httpx.Response:
    """parse_mode GONDERILMEZ -- v1 dersi (SS4.2): Markdown ozel karakterleri
    kamera adinda gecince Telegram 400 donduruyordu."""
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    with httpx.Client(transport=_transport, timeout=_TIMEOUT_SEC) as client:
        if photo_path is not None:
            with open(photo_path, "rb") as fh:
                files = {"photo": (photo_path.name, fh, "image/jpeg")}
                data = {"chat_id": chat_id, "caption": _truncate_caption(text_)}
                return client.post(f"{base}/sendPhoto", data=data, files=files)
        data = {"chat_id": chat_id, "text": text_}
        return client.post(f"{base}/sendMessage", data=data)


def _send_with_retry(chat_id: str, text_: str, photo_path: Path | None) -> tuple[str, str]:
    """SS4.3 yeniden deneme tablosu -- 3 deneme. 5xx/ag hatasi ustel geri
    cekilme (1 -> 2 -> 4 sn); 429 yanittaki retry_after kadar bekler (tavan
    30 sn); diger 4xx kalicidir, denenmez."""
    delay = 1.0
    last_error = ""
    for attempt in range(3):
        try:
            resp = _do_request(chat_id, text_, photo_path)
        except httpx.HTTPError as exc:
            last_error = str(exc)
            if attempt < 2:
                _sleep(delay)
                delay = min(delay * 2, 30.0)
            continue

        if resp.status_code == 200:
            try:
                ok = resp.json().get("ok")
            except ValueError:
                ok = False
            if ok:
                return "sent", ""
            last_error = resp.text[:240]
            break   # 200 ama ok degil -- Telegram govdesi bozuk, tekrar denemek anlamsiz
        if resp.status_code == 429:
            retry_after = 30.0
            try:
                retry_after = min(float(resp.json().get("parameters", {}).get("retry_after", 30)), 30.0)
            except (ValueError, TypeError, AttributeError):
                pass
            last_error = f"HTTP 429: {resp.text[:200]}"
            if attempt < 2:
                _sleep(retry_after)
            continue
        if 500 <= resp.status_code < 600:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if attempt < 2:
                _sleep(delay)
                delay = min(delay * 2, 30.0)
            continue
        # diger 4xx: kalici hata, denenmez
        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        break
    return "failed", last_error[:240]


def _is_armed(db, camera_id: int) -> bool:
    """Kameraya ozel satir varsa o, yoksa global satir; ikisi de yoksa
    KURULU sayilir. Cozum sirasi api/routers/settings.py ile aynidir
    (kamera satiri globali ezer); burada tek sorguda COALESCE ile yapilir
    cunku bildirim yolunda ikinci bir gidis gelis gereksizdir.

    Varsayilanin True olmasi bilinclidir: bir arizada (satir silinmis,
    sutun yok) sistemin SESSIZLESMEMESI gerekir. Guvenlik sisteminde
    guvenli taraf gurultulu olandir."""
    value = db.execute(text("""
        SELECT COALESCE(
            (SELECT armed FROM detection_settings WHERE camera_id = :cam),
            (SELECT armed FROM detection_settings WHERE camera_id IS NULL),
            TRUE)
    """), {"cam": camera_id}).scalar()
    # None -> True. `bool(None)` False verirdi, yani sorgu beklenmedik bicimde
    # bos donerse sistem KENDILIGINDEN sessizlesirdi -- yukaridaki gerekcenin
    # tam tersi. COALESCE bunu zaten onler ama tek savunma birakilmaz.
    return True if value is None else bool(value)


def _process_event(event_id: int) -> None:
    """SS4.6 sirasi: rapor ONCE yazilir (Telegram tamamen kapali olsa bile
    panel raporu gorur), sonra alicilar cozulup gonderilir."""
    with SessionLocal() as db:
        row = db.execute(
            text("""
                SELECT e.camera_id, e.anomaly_type, e.confidence, e.duration_ms,
                       e.started_at, e.track_ids, e.severity, e.frame_path,
                       c.name AS camera_name, z.name AS zone_name
                FROM events e
                JOIN cameras c ON c.id = e.camera_id
                LEFT JOIN zones z ON z.id = e.zone_id
                WHERE e.id = :id
            """), {"id": event_id},
        ).mappings().first()
        if row is None:
            return   # olay bulunamadi -- SS4.6 disi bir durum, sessizce cik

        # Kur/Birak (TEZ_KAPSAM.txt Faz 1). Evde modunda tespit, kanit ve
        # olay kaydi AYNEN surer; kesilen yalnizca disari bildirimdir.
        # LLM cagrisindan ONCE bakilir: kimseye gitmeyecek bir rapor icin
        # kota harcanmaz.
        if not _is_armed(db, row["camera_id"]):
            _counters["skipped"] += 1
            db.add(Notification(event_id=event_id, channel="telegram", target="-",
                                 status="skipped", error="evde modu"))
            db.commit()
            return

        ctx = {
            "event_id": event_id,
            "camera_name": row["camera_name"],
            "anomaly_type": row["anomaly_type"],
            "zone_name": row["zone_name"],
            "confidence": row["confidence"],
            "duration_sec": (row["duration_ms"] or 0) / 1000.0,
            "started_at": row["started_at"],
            "track_count": len(row["track_ids"] or []),
            "severity": row["severity"],
        }
        report_text, mode = generate_report(ctx)
        _counters[mode] += 1

        db.execute(text("UPDATE events SET llm_report_tr = :t WHERE id = :id"),
                   {"t": report_text, "id": event_id})
        db.commit()

        recipients = [r[0] for r in db.execute(text(
            "SELECT telegram_chat_id FROM users WHERE is_active AND "
            "telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''")).all()]
        if not recipients and TELEGRAM_CHAT_ID:
            recipients = [TELEGRAM_CHAT_ID]   # SS4.1: tez demosu icin tek alici yedegi
        if not recipients:
            print(f"  bildirim kanali yapilandirilmamis, olay {event_id} atlandi")
            return
        if not TELEGRAM_BOT_TOKEN:
            print(f"  TELEGRAM_BOT_TOKEN bos, olay {event_id} icin gonderim atlandi")
            return

        header = f"🚨 {(row['severity'] or '').upper()} — {row['camera_name']}\n"
        full_text = header + report_text
        photo_path = _resolve_photo_path(row["frame_path"])
        for chat_id in recipients:
            status_, error = _send_with_retry(chat_id, full_text, photo_path)
            _counters[status_] += 1
            db.add(Notification(event_id=event_id, channel="telegram", target=chat_id,
                                 status=status_, error=(error or None)))
        db.commit()


def _worker_loop() -> None:
    """Kuyruktan bir olay ISLER; govde ASLA olmez (SS4.5) -- genis except
    bilincli: bu iplik olurse bildirimler sessizce keser. ponytail: hiz siniri
    kuyruk ogesi (olay) basina uygulanir, ayni olayin birden fazla alicisi
    arasinda beklenmez -- coklu alicili demo yok, tek yapilandirilmis hedef
    yeterli; coklu alici gerekirse gonderim basina tasin."""
    last_sent = 0.0
    while True:
        event_id = _queue.get()
        if event_id is None:
            break
        wait = NOTIFY_MIN_INTERVAL_SEC - (time.monotonic() - last_sent)
        if wait > 0:
            _sleep(wait)
        try:
            _process_event(event_id)
        except Exception as exc:  # noqa: BLE001 -- SS4.5: iplik asla olmemeli
            print(f"  bildirim isleme hatasi (event {event_id}): {exc}")
        last_sent = time.monotonic()


def start() -> None:
    global _thread
    _thread = threading.Thread(target=_worker_loop, daemon=True)
    _thread.start()


def stop(timeout: float = 15.0) -> None:
    _queue.put(None)
    if _thread is not None:
        _thread.join(timeout=timeout)
    print(f"  bildirim kapandi -- gonderilen {_counters['sent']}  basarisiz {_counters['failed']}  "
          f"dusen {_counters['dropped']}  llm {_counters['llm']}  sablon {_counters['template']}")
