"""Layer 2 — Chat Engine controller.

`ChatController` is the orchestration point between:

* Layer 3 (`ChatService`) for validation, room/session rules, and rate
  limiting — pure logic, no I/O;
* Layer 4 (`ChatRepository`, `MessageBroker`) for persistence and
  cross-instance broadcasting;
* the transport-facing `ConnectionManager`, which tracks the WebSocket
  connections held open *by this process* and is therefore the one
  piece of chat state that must live in Layer 2 (it holds live
  `WebSocket` objects).

`chat_routes.py` stays a thin adapter over this class: it never
contains business logic itself, only request/response marshalling.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict

from fastapi import WebSocket

from ...layer_3_business.chat.chat_service import ChatService, MessageType
from ...layer_3_business.chat.exceptions import AlreadyJoinedError, NotAParticipantError
from ...layer_4_data_access.events.message_broker import MessageBroker, MessageBrokerError
from ...layer_4_data_access.repositories.chat_repository import ChatRepository
from ..schemas.chat_schemas import ChatHistoryResponse, ChatMessageResponse

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


class ChatController:
    """Coordinates Layer 3 business rules and Layer 4 persistence /
    broadcasting to serve the Chat Engine's WebSocket and REST
    endpoints."""

    def __init__(
        self,
        *,
        chat_service: ChatService,
        repository: ChatRepository,
        broker: MessageBroker,
        connection_manager: ConnectionManager | None = None,
    ) -> None:
        """Wires the controller to its collaborators.

        All three (`chat_service`, `repository`, `broker`) are
        injected rather than constructed here, so the controller can
        be exercised in tests with fakes/stubs for each — it never
        instantiates a concrete `ChatService`, database repository, or
        Redis client itself.
        """
        self._service = chat_service
        self._repository = repository
        self._broker = broker
        self._connections = connection_manager or ConnectionManager()
        self._relay_tasks: Dict[str, asyncio.Task[None]] = {}
        self._relay_lock = asyncio.Lock()
        self._pending_cleanup_tasks: set[asyncio.Task[None]] = set()

    # -- WebSocket lifecycle ------------------------------------------------

    async def connect_client(
        self, websocket: WebSocket, *, room_id: str, client_id: str
    ) -> None:
        """Accepts the WebSocket, joins the room (idempotently, so
        reconnects are harmless), and ensures a relay task is running
        so cross-instance broadcasts reach this client."""
        await self._connections.connect(room_id, client_id, websocket)
        await self._ensure_relay_task(room_id)

        room = await self._repository.get_or_create_room(room_id)
        try:
            self._service.join_room(room, client_id)
        except AlreadyJoinedError:
            return  # a reconnecting client is not an error

        await self._repository.save_room(room)
        await self._announce(
            room_id=room_id,
            content=f'"{client_id}" joined the room.',
            message_type=MessageType.JOIN,
        )

    def schedule_disconnect(self, *, room_id: str, client_id: str) -> None:
        """Runs `disconnect_client` as a tracked background task instead
        of awaiting it directly.

        WebSocket routes call this from a `finally` block, which may
        itself be in the process of being torn down/cancelled by the
        ASGI server as the connection closes. A plain `await` there
        could be cut off mid-write; scheduling the cleanup as an
        independent task lets it keep running on the event loop
        regardless of what happens to the caller, while `shutdown()`
        still guarantees every scheduled cleanup finishes before the
        app (and its DB/broker connections) shuts down.
        """
        task = asyncio.create_task(
            self.disconnect_client(room_id=room_id, client_id=client_id),
            name=f"chat-disconnect-{room_id}-{client_id}",
        )
        self._pending_cleanup_tasks.add(task)
        task.add_done_callback(self._pending_cleanup_tasks.discard)
        task.add_done_callback(self._log_cleanup_failure)

    def _log_cleanup_failure(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.exception(
                "Unhandled error during chat disconnect cleanup", exc_info=error
            )

    async def disconnect_client(self, *, room_id: str, client_id: str) -> None:
        """Unregisters the local connection and leaves the room. Safe
        to call even if the client was never fully joined."""
        await self._connections.disconnect(room_id, client_id)

        room = await self._repository.get_or_create_room(room_id)
        try:
            self._service.leave_room(room, client_id)
        except NotAParticipantError:
            return

        await self._repository.save_room(room)
        await self._announce(
            room_id=room_id,
            content=f'"{client_id}" left the room.',
            message_type=MessageType.LEAVE,
        )

    async def handle_client_message(
        self, *, room_id: str, client_id: str, content: str
    ) -> None:
        """Validates, persists, and broadcasts a message from
        `client_id`. Raises a `ChatDomainError` subclass (propagated
        from Layer 3) if the message is rejected — the caller (a
        WebSocket route) decides how to surface that to the client.
        """
        room = await self._repository.get_or_create_room(room_id)
        message = self._service.compose_message(
            room=room, sender_id=client_id, content=content
        )
        await self._repository.save_message(message)
        await self._broker.publish(room_id, message.to_dict())
        # Local delivery (including the sender's own echo) happens via
        # the relay task consuming this same publish, so there is a
        # single, ordered delivery path regardless of which server
        # instance a given recipient is connected to.

    # -- REST history -----------------------------------------------------

    async def get_history(self, *, room_id: str, limit: int = 50) -> ChatHistoryResponse:
        """Fetches up to `limit` messages for `room_id` from Layer 4/5,
        re-applies Layer 3's ordering rules, and maps the result to the
        REST response schema — including whether older messages exist
        beyond this page.
        """
        raw_messages = await self._repository.get_history(room_id, limit=limit + 1)
        page = self._service.build_history_page(raw_messages, limit=limit)
        has_more = len(raw_messages) > len(page)

        return ChatHistoryResponse(
            room_id=room_id,
            messages=[
                ChatMessageResponse.model_validate(message.to_dict())
                for message in page
            ],
            has_more=has_more,
        )

    # -- Cross-instance relay -----------------------------------------------

    async def _announce(
        self, *, room_id: str, content: str, message_type: MessageType
    ) -> None:
        notice = self._service.build_system_message(
            room_id=room_id, content=content, message_type=message_type
        )
        await self._repository.save_message(notice)
        await self._broker.publish(room_id, notice.to_dict())

    async def _ensure_relay_task(self, room_id: str) -> None:
        async with self._relay_lock:
            existing = self._relay_tasks.get(room_id)
            if existing is not None and not existing.done():
                return
            self._relay_tasks[room_id] = asyncio.create_task(
                self._relay_loop(room_id), name=f"chat-relay-{room_id}"
            )

    async def _relay_loop(self, room_id: str) -> None:
        """Subscribes to `room_id` on the message broker for as long
        as this process holds at least one connection to it, fanning
        every published message out to local WebSocket clients."""
        try:
            async with self._broker.subscribe(room_id) as messages:
                async for payload in messages:
                    envelope = self._to_outgoing_envelope(payload)
                    await self._connections.broadcast_local(room_id, envelope)
        except asyncio.CancelledError:
            raise
        except MessageBrokerError:
            logger.exception(
                "Message broker relay for room %s stopped unexpectedly", room_id
            )

    @staticmethod
    def _to_outgoing_envelope(payload: dict) -> dict:
        """Wraps a raw `ChatMessage.to_dict()` payload in the
        `WebSocketOutgoingMessage` envelope shape clients expect:
        `{"type": "message" | "system", "data": {...}}`, distinguishing
        participant-authored text from server-generated join/leave
        notices."""
        outer_type = "message" if payload.get("type") == "text" else "system"
        return {"type": outer_type, "data": payload}

    async def shutdown(self) -> None:
        """Cancels every relay task and waits for any still-pending
        disconnect cleanup to finish. Call during application shutdown,
        before disposing the database engine or the message broker."""
        relay_tasks = list(self._relay_tasks.values())
        for task in relay_tasks:
            task.cancel()
        if relay_tasks:
            await asyncio.gather(*relay_tasks, return_exceptions=True)
        self._relay_tasks.clear()

        if self._pending_cleanup_tasks:
            await asyncio.gather(*self._pending_cleanup_tasks, return_exceptions=True)
