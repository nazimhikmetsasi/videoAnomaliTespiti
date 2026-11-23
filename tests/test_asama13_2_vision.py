"""Paket G: kamera basina WS istemci sayaci ve seed kaynak yolu."""

from __future__ import annotations

import asyncio
import datetime
import socket
import sys
from pathlib import Path

import jwt
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seed_pilot import PILOT_DIR, ROOT, source_value  # noqa: E402
from vision.ws_server import StreamServer  # noqa: E402

SECRET = "test-secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(cond, timeout=3.0) -> bool:
    import time
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_clients_counted_per_camera() -> None:
    port = _free_port()
    server = StreamServer(host="127.0.0.1", port=port, jwt_secret=SECRET)
    server.start()
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    tok = jwt.encode({"sub": "1", "exp": exp}, SECRET, algorithm="HS256")

    async def run() -> None:
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws/live/cam_a?token={tok}"):
            assert await asyncio.to_thread(
                _wait, lambda: server.clients("live", "cam_a") == 1)
            assert server.clients("live", "cam_b") == 0
            assert server.clients("meta", "cam_a") == 0
            assert server.live_clients == 1
        # the handler notices the close on its next send, so publish one frame
        server.publish_frame("cam_a", b"x")
        assert await asyncio.to_thread(
            _wait, lambda: server.clients("live", "cam_a") == 0)

    try:
        assert _wait(lambda: server._loop is not None and server._stop_event is not None)
        asyncio.run(run())
    finally:
        server.stop()


def test_seed_source_relative() -> None:
    clips = sorted(PILOT_DIR.glob("*.mp4")) if PILOT_DIR.exists() else []
    for clip in clips:
        v = source_value(clip)
        assert not Path(v).is_absolute() and "\\" not in v
        assert v == f"data/pilot/{clip.name}"
        assert (ROOT / v).is_file()
    # data/pilot is gitignored; the pure helper is still checked without files
    assert source_value(ROOT / "data" / "pilot" / "x.mp4") == "data/pilot/x.mp4"
