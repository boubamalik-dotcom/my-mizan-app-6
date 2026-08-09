"""Layer 2 — process-local WebSocket connection registry, shared by
every real-time feature.

Extracted from the Chat Engine when clinic queues needed the same
bookkeeping. There is deliberately one implementation rather than one
per feature: tracking which sockets are open, replacing a stale
connection on reconnect, and dropping a socket that fails mid-send are
all easy to get subtly wrong, and two copies would drift.

Deliberately process-local. Fan-out *across* processes is the message
broker's job (`layer_4_data_access/events/message_broker.py`); this
class only knows about the connections this one worker is holding open.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks the WebSocket connections held open by *this* server
    process, keyed by room then client id.

    Deliberately process-local: fan-out across processes is handled by
    `MessageBroker`, not by this class.
    """

    def __init__(self) -> None:
        """Creates an empty connection registry."""
        self._connections: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: str, client_id: str, websocket: WebSocket) -> None:
        """Accepts `websocket` and registers it under `room_id`/
        `client_id`, replacing any prior connection for the same pair
        (e.g. a stale connection from a dropped reconnect)."""
        await websocket.accept()
        async with self._lock:
            self._connections[room_id][client_id] = websocket

    async def disconnect(self, room_id: str, client_id: str) -> None:
        """Removes the registered connection for `client_id` in
        `room_id`, if any. Safe to call for an already-removed or
        never-registered pair."""
        async with self._lock:
            room_connections = self._connections.get(room_id)
            if room_connections is None:
                return
            room_connections.pop(client_id, None)
            if not room_connections:
                self._connections.pop(room_id, None)

    async def broadcast_local(self, room_id: str, payload: dict) -> None:
        """Sends `payload` to every client this process is holding a
        connection for in `room_id`. Connections that fail to receive
        the message are dropped."""
        async with self._lock:
            targets = list(self._connections.get(room_id, {}).items())

        for client_id, websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 - any send failure means a dead socket
                logger.info(
                    "Dropping unresponsive connection for client %s in room %s",
                    client_id,
                    room_id,
                )
                await self.disconnect(room_id, client_id)

    def has_local_connections(self, room_id: str) -> bool:
        """Whether this process currently holds at least one open
        connection for `room_id`."""
        return bool(self._connections.get(room_id))
