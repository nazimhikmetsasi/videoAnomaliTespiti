"""Asama 7 oz kontrolu - agsiz, DB'siz, sadece assert + httpx.MockTransport.

Calistirma:
    venv\\Scripts\\python.exe tests/test_notify.py

Zamanlama testleri gercek time.sleep CAGIRMAZ: api.notify._sleep modul
degiskeni her testte yamanip eski degeriyle geri konur (ASAMA7_PLAN.md SS8).
Ag testleri api.notify._transport'i httpx.MockTransport ile degistirir.
"""

from __future__ import annotations

import queue as queue_mod
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import api.notify as notify  # noqa: E402
import api.storage_paths as storage_paths  # noqa: E402


def _patch(**kwargs):
    old = {name: getattr(notify, name) for name in kwargs}
    for name, value in kwargs.items():
        setattr(notify, name, value)
    return old


def _restore(old: dict) -> None:
    for name, value in old.items():
        setattr(notify, name, value)


# ------------------------------------------------------------ _resolve_photo_path
def test_resolve_photo_path_none_when_frame_path_missing() -> None:
    assert notify._resolve_photo_path(None) is None
    assert notify._resolve_photo_path("") is None


def test_resolve_photo_path_none_when_file_not_on_disk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_root = storage_paths._STORAGE_ROOT
        storage_paths._STORAGE_ROOT = Path(tmp).resolve()
        try:
            assert notify._resolve_photo_path("frames/does_not_exist.jpg") is None
        finally:
            storage_paths._STORAGE_ROOT = old_root


def test_resolve_photo_path_returns_path_when_file_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_root = storage_paths._STORAGE_ROOT
        storage_paths._STORAGE_ROOT = Path(tmp).resolve()
        (Path(tmp) / "frames").mkdir()
        frame = Path(tmp) / "frames" / "cam1_FALL_1.jpg"
        frame.write_bytes(b"fake-jpeg")
        try:
            result = notify._resolve_photo_path("frames/cam1_FALL_1.jpg")
        finally:
            storage_paths._STORAGE_ROOT = old_root
        assert result == frame.resolve()


# ------------------------------------------------------------ _truncate_caption
def test_truncate_caption_over_1000_chars_is_clipped() -> None:
    long_text = "a" * 1500
    truncated = notify._truncate_caption(long_text)
    assert len(truncated) == 1001
    assert truncated.endswith("…")


def test_truncate_caption_under_limit_is_unchanged() -> None:
    text = "kısa rapor metni."
    assert notify._truncate_caption(text) == text


# ------------------------------------------------------------ _send_with_retry (endpoint secimi)
def test_send_with_retry_uses_sendphoto_when_photo_given() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    with tempfile.TemporaryDirectory() as tmp:
        photo = Path(tmp) / "frame.jpg"
        photo.write_bytes(b"fake-jpeg")
        old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler))
        try:
            status_, error = notify._send_with_retry("123", "rapor metni", photo)
        finally:
            _restore(old)
    assert status_ == "sent"
    assert error == ""
    assert "sendPhoto" in urls[0]


def test_send_with_retry_uses_sendmessage_when_no_photo() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler))
    try:
        status_, error = notify._send_with_retry("123", "rapor metni", None)
    finally:
        _restore(old)
    assert status_ == "sent"
    assert "sendMessage" in urls[0]


# ------------------------------------------------------------ yeniden deneme tablosu
def test_send_with_retry_500_three_attempts_then_failed() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="internal error")

    sleeps: list[float] = []
    old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler),
                 _sleep=lambda s: sleeps.append(s))
    try:
        status_, error = notify._send_with_retry("123", "rapor", None)
    finally:
        _restore(old)
    assert status_ == "failed"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]   # son denemeden sonra beklenmez


def test_send_with_retry_400_single_attempt_then_failed() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, text="bad request")

    def _fail_if_called(delay: float) -> None:
        raise AssertionError(f"uyunmamali ama sleep({delay}) cagrildi")

    old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler),
                 _sleep=_fail_if_called)
    try:
        status_, error = notify._send_with_retry("123", "rapor", None)
    finally:
        _restore(old)
    assert status_ == "failed"
    assert len(calls) == 1


def test_send_with_retry_429_reads_retry_after_then_retries() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"parameters": {"retry_after": 2}})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler),
                 _sleep=lambda s: sleeps.append(s))
    try:
        status_, error = notify._send_with_retry("123", "rapor", None)
    finally:
        _restore(old)
    assert status_ == "sent"
    assert sleeps == [2.0]
    assert len(calls) == 2


def test_send_with_retry_ok_true_returns_sent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    old = _patch(TELEGRAM_BOT_TOKEN="test-token", _transport=httpx.MockTransport(handler))
    try:
        status_, error = notify._send_with_retry("123", "rapor", None)
    finally:
        _restore(old)
    assert status_ == "sent"


# ------------------------------------------------------------ kuyruk
def test_enqueue_drops_oldest_when_queue_full() -> None:
    old_queue = notify._queue
    old_dropped = notify._counters["dropped"]
    notify._queue = queue_mod.Queue(maxsize=2)
    try:
        notify.enqueue(1)
        notify.enqueue(2)
        notify.enqueue(3)   # kuyruk dolu -- en eski (1) dusmeli
        remaining = []
        while not notify._queue.empty():
            remaining.append(notify._queue.get_nowait())
    finally:
        notify._queue = old_queue
    assert remaining == [2, 3]
    assert notify._counters["dropped"] == old_dropped + 1


# ------------------------------------------------------------ worker govdesi
def test_worker_loop_survives_exception_in_one_event() -> None:
    processed: list[int] = []

    def fake_process(event_id: int) -> None:
        if event_id == 1:
            raise RuntimeError("simule hata")
        processed.append(event_id)

    old_queue = notify._queue
    notify._queue = queue_mod.Queue(maxsize=200)
    notify._queue.put(1)
    notify._queue.put(2)
    notify._queue.put(None)   # sentinel: dongu bitsin

    old = _patch(_process_event=fake_process, NOTIFY_MIN_INTERVAL_SEC=0.0, _sleep=lambda s: None)
    try:
        notify._worker_loop()
    finally:
        _restore(old)
        notify._queue = old_queue
    assert processed == [2]   # 1 istisna firlatti ama iplik olmedi, 2 yine islendi


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [OK]   {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [HATA] {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  [HATA] {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n  {len(tests) - failed}/{len(tests)} gecti")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
