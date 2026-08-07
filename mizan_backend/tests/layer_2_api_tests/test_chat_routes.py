"""End-to-end tests for the Chat Engine's Layer 2 HTTP + WebSocket
routes.

Wires a real `ChatController` (Layer 3 `ChatService` + Layer 5
SQLite-backed repository + Layer 4 Redis broker against the local
Redis instance) behind a bare FastAPI test app, so these tests
exercise the full request path — including a real Redis publish/
subscribe round trip — without depending on the production
composition root in `main.py`.

Skipped automatically if no local Redis server is reachable.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.layer_2_api.main_router import api_router
from src.layer_2_api.controllers.chat_controller import ChatController
from src.layer_3_business.chat.chat_service import ChatService, MessageRateLimiter
from src.layer_4_data_access.events.message_broker import RedisMessageBroker
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.implementations.chat_repository_impl import (
    SqlAlchemyChatRepository,
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


async def _redis_available() -> bool:
    try:
        client = redis.from_url(REDIS_URL)
        await asyncio.wait_for(client.ping(), timeout=1.0)
        await client.aclose()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not asyncio.run(_redis_available()),
    reason="No Redis server reachable for integration test.",
)

pytestmark = requires_redis


# NOTE: every async resource below (the Redis client, the SQLAlchemy
# engine, and the ChatController's background relay tasks) is built
# and torn down *inside* the ASGI lifespan, rather than in a
# `pytest_asyncio` fixture. `TestClient` runs the whole ASGI app
# (including its lifespan) on its own internally-managed event loop in
# a background thread; constructing these resources on a *different*
# loop (e.g. pytest-asyncio's) would bind their internal futures/locks
# to the wrong loop and hang forever the first time a request used
# them. Routing everything through the lifespan keeps every bit of
# async state on the one loop that actually serves requests.
@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = build_session_factory(engine)
    repository = SqlAlchemyChatRepository(session_factory, default_max_participants=10)

    broker = RedisMessageBroker(REDIS_URL, channel_prefix=f"test-routes:{uuid.uuid4()}:")
    await broker.connect()

    # A generous rate limit so the test suite itself never trips it.
    service = ChatService(rate_limiter=MessageRateLimiter(max_messages=1000))
    controller = ChatController(chat_service=service, repository=repository, broker=broker)
    app.state.chat_controller = controller

    try:
        yield
    finally:
        await controller.shutdown()
        await broker.disconnect()
        await engine.dispose()


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI(lifespan=_test_lifespan)
    application.include_router(api_router, prefix="/api/v1")
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_get_history_for_new_room_is_empty(client: TestClient) -> None:
    response = client.get("/api/v1/chat/rooms/room-empty/messages")

    assert response.status_code == 200
    body = response.json()
    assert body == {"room_id": "room-empty", "messages": [], "has_more": False}


def test_websocket_connect_receives_join_announcement(client: TestClient) -> None:
    with client.websocket_connect(
        "/api/v1/chat/ws/chat/alice?room_id=room-1"
    ) as websocket:
        event = websocket.receive_json()

        assert event["type"] == "system"
        assert "alice" in event["data"]["content"]
        assert event["data"]["type"] == "join"


def test_websocket_send_message_is_echoed_back_and_persisted(
    client: TestClient,
) -> None:
    with client.websocket_connect(
        "/api/v1/chat/ws/chat/alice?room_id=room-2"
    ) as websocket:
        websocket.receive_json()  # join announcement

        websocket.send_json({"type": "message", "content": "hello, world"})
        event = websocket.receive_json()

        assert event["type"] == "message"
        assert event["data"]["content"] == "hello, world"
        assert event["data"]["sender_id"] == "alice"

    history_response = client.get("/api/v1/chat/rooms/room-2/messages")
    messages = history_response.json()["messages"]
    text_messages = [m for m in messages if m["type"] == "text"]
    assert len(text_messages) == 1
    assert text_messages[0]["content"] == "hello, world"


def test_websocket_ping_receives_pong(client: TestClient) -> None:
    with client.websocket_connect(
        "/api/v1/chat/ws/chat/alice?room_id=room-3"
    ) as websocket:
        websocket.receive_json()  # join announcement

        websocket.send_json({"type": "ping"})
        event = websocket.receive_json()

        assert event == {"type": "pong"}


def test_websocket_rejects_malformed_frame_without_disconnecting(
    client: TestClient,
) -> None:
    with client.websocket_connect(
        "/api/v1/chat/ws/chat/alice?room_id=room-4"
    ) as websocket:
        websocket.receive_json()  # join announcement

        websocket.send_json({"type": "not-a-real-type"})
        error_event = websocket.receive_json()
        assert error_event["type"] == "error"

        # The connection should still be usable afterwards.
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}


def test_two_clients_in_same_room_receive_each_others_messages(
    client: TestClient,
) -> None:
    with client.websocket_connect(
        "/api/v1/chat/ws/chat/alice?room_id=room-5"
    ) as ws_alice:
        ws_alice.receive_json()  # alice's own join announcement

        with client.websocket_connect(
            "/api/v1/chat/ws/chat/bob?room_id=room-5"
        ) as ws_bob:
            # Both clients observe bob joining.
            assert "bob" in ws_alice.receive_json()["data"]["content"]
            assert "bob" in ws_bob.receive_json()["data"]["content"]

            ws_alice.send_json({"type": "message", "content": "hi bob"})

            # Delivered to the sender too (single source of truth via
            # the broker relay) and to the other participant.
            message_for_alice = ws_alice.receive_json()
            message_for_bob = ws_bob.receive_json()

            assert message_for_alice["data"]["content"] == "hi bob"
            assert message_for_bob["data"]["content"] == "hi bob"
            assert message_for_alice["data"]["sender_id"] == "alice"


def test_get_history_rejects_invalid_limit(client: TestClient) -> None:
    response = client.get("/api/v1/chat/rooms/room-1/messages?limit=0")
    assert response.status_code == 422
