"""Asama 13.7 Paket G: StreamServer._check (jeton iptali). Gercek ag yok."""

from __future__ import annotations

import asyncio
import time

import jwt

from vision import ws_server
from vision.ws_server import REVALIDATE_SEC, StreamServer

SECRET = "x" * 32


def _tok(secret: str = SECRET) -> str:
    return jwt.encode({"sub": "1", "exp": int(time.time()) + 600}, secret, algorithm="HS256")


class _Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


def _server(status, clock=None):
    """status: int ya da istisna; cagri sayisi srv.calls'ta."""
    srv = StreamServer(jwt_secret=SECRET, api_url="http://api", clock=clock or _Clock())
    srv.calls = 0

    async def fake(token):
        srv.calls += 1
        if isinstance(status, Exception):
            raise status
        return status

    srv._api_status = fake
    return srv


def _run(coro):
    return asyncio.run(coro)


def test_no_api_url_local_signature_only() -> None:
    srv = StreamServer(jwt_secret=SECRET)
    assert _run(srv._check(_tok())) is True
    assert _run(srv._check(_tok("y" * 32))) is False
    assert _run(srv._check(None)) is False


def test_api_200_accept_401_reject_403_reject() -> None:
    assert _run(_server(200)._check(_tok())) is True
    assert _run(_server(401)._check(_tok())) is False
    assert _run(_server(403)._check(_tok())) is False


def test_network_error_and_5xx_fail_open(capsys) -> None:
    srv = _server(OSError("down"))
    assert _run(srv._check(_tok())) is True
    assert srv.api_failures == 1
    assert "basarisiz" in capsys.readouterr().out
    srv5 = _server(503)
    assert _run(srv5._check(_tok())) is True and srv5.api_failures == 1
    _run(srv5._check(_tok()))
    assert srv5.api_failures == 2
    assert capsys.readouterr().out.count("basarisiz") == 1   # tek uyari


def test_cache_within_window_then_refresh() -> None:
    clock = _Clock()
    srv = _server(200, clock)
    tok = _tok()
    assert _run(srv._check(tok)) and srv.calls == 1
    clock.t += REVALIDATE_SEC - 1
    assert _run(srv._check(tok)) and srv.calls == 1
    clock.t += 2
    assert _run(srv._check(tok)) and srv.calls == 2


def test_revocation_seen_after_window() -> None:
    clock = _Clock()
    srv = _server(200, clock)
    tok = _tok()
    assert _run(srv._check(tok)) is True
    srv._api_status = lambda t: _async(401)
    clock.t += REVALIDATE_SEC + 1
    assert _run(srv._check(tok)) is False


async def _async(v):
    return v


def test_bad_signature_never_calls_api() -> None:
    srv = _server(200)
    assert _run(srv._check(_tok("y" * 32))) is False
    assert srv.calls == 0


def test_cache_cap_pruned(monkeypatch) -> None:
    monkeypatch.setattr(ws_server, "_CACHE_CAP", 3)
    clock = _Clock()
    srv = _server(200, clock)
    for i in range(5):
        tok = jwt.encode({"sub": str(i)}, SECRET, algorithm="HS256")
        _run(srv._check(tok))
        clock.t += 1
    assert len(srv._token_cache) <= 3
