"""WebSocket connection manager bridged to Redis pub/sub for real-time queue updates.

Flow:
    1. Clients (React dashboard, Flutter app) open a WebSocket to
       `/ws/clinics/{clinic_id}` and are registered in `active_connections`.
    2. On the first connection for a given `clinic_id`, a background task
       subscribes to that clinic's Redis channel (`clinic_queue_{clinic_id}`)
       via `pubsub_listener`.
    3. Whenever `POST /clinics/{clinic_id}/next` updates the database, it
       calls `broadcast_queue_update`, which publishes the new queue state to
       that Redis channel.
    4. Every process running `pubsub_listener` for that clinic receives the
       message and forwards it to its own locally-connected WebSockets.

Using Redis as the fan-out layer (rather than broadcasting directly to
`active_connections`) means the real-time updates stay correct even if the
API is horizontally scaled across multiple backend processes/replicas.
"""
import asyncio
import json
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[UUID, list[WebSocket]] = {}
        self.redis: redis.Redis | None = None
        self._listener_tasks: dict[UUID, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Redis lifecycle
    # ------------------------------------------------------------------
    async def connect_redis(self, redis_url: str) -> None:
        """Set up the Redis connection. Call once on application startup."""
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def close_redis(self) -> None:
        """Cancel all pub/sub listener tasks and close the Redis connection."""
        for task in self._listener_tasks.values():
            task.cancel()
        self._listener_tasks.clear()

        if self.redis is not None:
            await self.redis.close()
            self.redis = None

    # ------------------------------------------------------------------
    # WebSocket connection management
    # ------------------------------------------------------------------
    async def connect(self, websocket: WebSocket, clinic_id: UUID) -> None:
        """Accept a WebSocket connection and register it for a clinic."""
        await websocket.accept()
        self.active_connections.setdefault(clinic_id, []).append(websocket)

        # Start one Redis subscription per clinic_id, shared by every
        # WebSocket connected to that clinic on this process.
        if clinic_id not in self._listener_tasks:
            self._listener_tasks[clinic_id] = asyncio.create_task(self.pubsub_listener(clinic_id))

    def disconnect(self, websocket: WebSocket, clinic_id: UUID) -> None:
        """Remove a closed/disconnected WebSocket from the manager."""
        connections = self.active_connections.get(clinic_id)
        if not connections:
            return

        if websocket in connections:
            connections.remove(websocket)

        if not connections:
            self.active_connections.pop(clinic_id, None)
            task = self._listener_tasks.pop(clinic_id, None)
            if task is not None:
                task.cancel()

    # ------------------------------------------------------------------
    # Redis <-> WebSocket bridge
    # ------------------------------------------------------------------
    async def pubsub_listener(self, clinic_id: UUID) -> None:
        """Subscribe to `clinic_queue_{clinic_id}` and forward messages to local sockets."""
        if self.redis is None:
            raise RuntimeError("Redis connection is not initialized")

        channel_name = f"clinic_queue_{clinic_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                await self._send_to_local_sockets(clinic_id, message["data"])
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    async def _send_to_local_sockets(self, clinic_id: UUID, raw_message: str) -> None:
        connections = self.active_connections.get(clinic_id, [])
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_text(raw_message)
            except Exception:
                stale.append(websocket)

        for websocket in stale:
            self.disconnect(websocket, clinic_id)

    async def broadcast_queue_update(self, clinic_id: UUID, queue: list[dict[str, Any]]) -> None:
        """Publish the clinic's updated queue state to its Redis channel."""
        if self.redis is None:
            raise RuntimeError("Redis connection is not initialized")

        channel_name = f"clinic_queue_{clinic_id}"
        payload = {
            "event": "queue_updated",
            "clinic_id": str(clinic_id),
            "queue": queue,
        }
        await self.redis.publish(channel_name, json.dumps(payload))
