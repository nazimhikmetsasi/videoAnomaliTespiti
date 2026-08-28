"""Bagli WebSocket istemcilerinin kumesi ve yayini (docs/ASAMA6_PLAN.md SS8.4).
Tek sinif, kucuk metot kumesi -- /ws/alerts bugun tek kullanicisidir.
"""

from __future__ import annotations

import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        """Kopan istemciler sessizce kumeden cikarilir -- bir istemcinin
        gonderim hatasi digerlerinin yayinini durdurmamali."""
        if not self._clients:
            return
        data = json.dumps(payload, default=str)
        dead = set()
        for ws in self._clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._clients -= dead
