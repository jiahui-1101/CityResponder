"""In-process WebSocket connection manager."""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track connected clients and broadcast JSON messages to them."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, *, user_id: int, role: str) -> None:
        """Accept and register an authenticated WebSocket connection."""

        await websocket.accept()
        self._connections[websocket] = {"user_id": user_id, "role": role}

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection if it is currently registered."""

        self._connections.pop(websocket, None)

    def connected_count(self) -> int:
        """Return the number of currently registered live clients."""

        return len(self._connections)

    async def broadcast_json(self, message: Mapping[str, Any]) -> None:
        """Send a JSON message and remove clients that can no longer receive it."""

        for websocket in tuple(self._connections):
            try:
                await websocket.send_json(dict(message))
            except Exception:
                logger.warning("Removing unavailable live WebSocket client", exc_info=True)
                self.disconnect(websocket)


live_connection_manager = ConnectionManager()
