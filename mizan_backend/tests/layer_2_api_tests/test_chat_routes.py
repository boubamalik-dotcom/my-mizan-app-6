"""End-to-end tests for the Chat Engine's Layer 2 HTTP + WebSocket
routes, including JWT-based authentication of the WebSocket
connection.

Wires a real `ChatController` (Layer 3 `ChatService` + Layer 5
SQLite-backed repository + Layer 4 Redis broker against the local
Redis instance) and a real `AuthService` behind a bare FastAPI test
app, so these tests exercise the full request path — including a real
Redis publish/subscribe round trip — without depending on the
production composition root in `main.py`.

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
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.main_router import api_router
from src.layer_2_api.controllers.chat_controller import ChatController
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.chat.chat_service import ChatService, MessageRateLimiter
from src.layer_4_data_access.events.message_broker import RedisMessageBroker
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.implementations.chat_repository_impl import (
    SqlAlchemyChatRepository,
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"


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

    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    auth_service = AuthService(secret_key=TEST_SECRET_KEY)

    # A generous rate limit so the test suite itself never trips it.
    service = ChatService(rate_limiter=MessageRateLimiter(max_messages=1000))
    controller = ChatController(chat_service=service, repository=repository, broker=broker)
    app.state.chat_controller = controller
    app.state.auth_service = auth_service
    # Needed by `get_current_user` (via `get_auth_controller`), which
    # `GET /chat/history/{client_id}` depends on — registration/login
    # go through the same real `/auth/*` routes used in production.
    app.state.auth_controller = AuthController(
        auth_service=auth_service, unit_of_work_factory=unit_of_work_factory
    )

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


def _token_for(client_id: str) -> str:
    """Issues a real, validly-signed access token whose subject is
    `client_id` — the WebSocket route requires the token's subject to
    match the `{client_id}` path segment being connected as."""
    return AuthService(secret_key=TEST_SECRET_KEY).create_access_token(subject=client_id)


def _ws_url(client_id: str, *, room_id: str, token: str | None) -> str:
    url = f"/api/v1/chat/ws/chat/{client_id}?room_id={room_id}"
    if token is not None:
        url += f"&token={token}"
    return url


def _register_and_login(client: TestClient, *, email: str) -> str:
    """Registers a real account (unlike `_token_for`, which mints a
    token for an arbitrary subject with no backing account) and logs
    in, returning its access token.

    `GET /chat/history/{client_id}` depends on `get_current_user`,
    which resolves the token's subject to a real, persisted user —
    so, unlike the WebSocket route (which only decodes the token),
    exercising it requires an account created through the real
    `/auth/register` + `/auth/login` flow.
    """
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _history_url(client_id: str, *, room_id: str, limit: int | None = None) -> str:
    url = f"/api/v1/chat/history/{client_id}?room_id={room_id}"
    if limit is not None:
        url += f"&limit={limit}"
    return url


def test_get_history_for_new_room_is_empty(client: TestClient) -> None:
    token = _register_and_login(client, email="history-reader@example.com")
    response = client.get(
        _history_url("history-reader@example.com", room_id="room-empty"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"room_id": "room-empty", "messages": [], "has_more": False}


def test_websocket_connect_receives_join_announcement(client: TestClient) -> None:
    with client.websocket_connect(
        _ws_url("alice", room_id="room-1", token=_token_for("alice"))
    ) as websocket:
        event = websocket.receive_json()

        assert event["type"] == "system"
        assert "alice" in event["data"]["content"]
        assert event["data"]["type"] == "join"


def test_websocket_send_message_is_echoed_back_and_persisted(
    client: TestClient,
) -> None:
    client_id = "alice-history@example.com"
    token = _register_and_login(client, email=client_id)

    with client.websocket_connect(
        _ws_url(client_id, room_id="room-2", token=token)
    ) as websocket:
        websocket.receive_json()  # join announcement

        websocket.send_json({"type": "message", "content": "hello, world"})
        event = websocket.receive_json()

        assert event["type"] == "message"
        assert event["data"]["content"] == "hello, world"
        assert event["data"]["sender_id"] == client_id

    history_response = client.get(
        _history_url(client_id, room_id="room-2"), headers=_auth_headers(token)
    )
    messages = history_response.json()["messages"]
    text_messages = [m for m in messages if m["type"] == "text"]
    assert len(text_messages) == 1
    assert text_messages[0]["content"] == "hello, world"


def test_client_can_reconnect_after_disconnecting(client: TestClient) -> None:
    """Reconnecting to a room must work as many times as the client
    likes.

    Leaving soft-deletes the `chat_participants` row (`left_at` is
    stamped, the row stays), and `(thread_id, user_id)` is unique — so
    re-joining used to attempt a second INSERT, raise `IntegrityError`,
    and get turned into a `WS_1011_INTERNAL_ERROR` close by this route's
    catch-all. The practical effect was that any client could join a
    given room only once per lifetime: after their first disconnect,
    every later connection was accepted and then immediately killed.
    """
    client_id = "reconnector@example.com"
    token = _register_and_login(client, email=client_id)

    for attempt in range(3):
        with client.websocket_connect(
            _ws_url(client_id, room_id="room-reconnect", token=token)
        ) as websocket:
            # Reaching a usable connection is the assertion: a failed
            # rejoin closes the socket instead of answering.
            websocket.send_json({"type": "ping"})

            event = websocket.receive_json()
            while event["type"] != "pong":
                assert event["type"] != "error", f"attempt {attempt}: {event}"
                event = websocket.receive_json()

            assert event == {"type": "pong"}, f"attempt {attempt}"


def test_websocket_ping_receives_pong(client: TestClient) -> None:
    with client.websocket_connect(
        _ws_url("alice", room_id="room-3", token=_token_for("alice"))
    ) as websocket:
        websocket.receive_json()  # join announcement

        websocket.send_json({"type": "ping"})
        event = websocket.receive_json()

        assert event == {"type": "pong"}


def test_websocket_rejects_malformed_frame_without_disconnecting(
    client: TestClient,
) -> None:
    with client.websocket_connect(
        _ws_url("alice", room_id="room-4", token=_token_for("alice"))
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
        _ws_url("alice", room_id="room-5", token=_token_for("alice"))
    ) as ws_alice:
        ws_alice.receive_json()  # alice's own join announcement

        with client.websocket_connect(
            _ws_url("bob", room_id="room-5", token=_token_for("bob"))
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
    token = _register_and_login(client, email="limit-tester@example.com")
    response = client.get(
        _history_url("limit-tester@example.com", room_id="room-1", limit=0),
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


class TestWebSocketAuthentication:
    """Security tests for the `?token=` query-parameter authentication
    the Chat WebSocket endpoint requires, per the "secure the
    perimeter" hardening pass: a connection is rejected — with
    `websocket.close(code=status.WS_1008_POLICY_VIOLATION)`, before
    `ChatController.connect_client` (and therefore `websocket.accept`)
    is ever reached — for a missing token, an invalid/expired token,
    or a token that authenticates a *different* identity than the
    `{client_id}` path segment being connected as.
    """

    def test_connection_is_instantly_closed_when_token_is_missing(
        self, client: TestClient
    ) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                _ws_url("alice", room_id="room-auth-1", token=None)
            ) as websocket:
                websocket.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_connection_is_instantly_closed_for_a_malformed_token(
        self, client: TestClient
    ) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                _ws_url("alice", room_id="room-auth-2", token="not-a-real-jwt")
            ) as websocket:
                websocket.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_connection_is_instantly_closed_for_a_token_signed_with_a_different_secret(
        self, client: TestClient
    ) -> None:
        forged_token = AuthService(
            secret_key="a-totally-different-secret-key!!!"
        ).create_access_token(subject="alice")

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                _ws_url("alice", room_id="room-auth-3", token=forged_token)
            ) as websocket:
                websocket.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_connection_is_instantly_closed_for_an_expired_token(
        self, client: TestClient
    ) -> None:
        import time

        expired_service = AuthService(
            secret_key=TEST_SECRET_KEY, access_token_expire_minutes=0
        )
        expired_token = expired_service.create_access_token(subject="alice")
        time.sleep(1.1)  # ensure the expiry timestamp has actually passed

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                _ws_url("alice", room_id="room-auth-4", token=expired_token)
            ) as websocket:
                websocket.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_connection_is_instantly_closed_when_token_subject_does_not_match_client_id(
        self, client: TestClient
    ) -> None:
        """A valid token for "bob" must not authorize connecting as
        "alice" — otherwise any authenticated user could impersonate
        any other client id simply by changing the URL path."""
        bobs_token = _token_for("bob")

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                _ws_url("alice", room_id="room-auth-5", token=bobs_token)
            ) as websocket:
                websocket.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

    def test_connection_succeeds_with_a_valid_matching_token(
        self, client: TestClient
    ) -> None:
        """Sanity check that the authentication gate itself isn't
        over-broad: a valid token whose subject matches `client_id`
        must still be able to connect normally."""
        with client.websocket_connect(
            _ws_url("alice", room_id="room-auth-6", token=_token_for("alice"))
        ) as websocket:
            event = websocket.receive_json()
            assert event["type"] == "system"


class TestChatHistoryAuthorization:
    """Security tests for `GET /chat/history/{client_id}`: it must
    require a valid access token (via `get_current_user`, just like
    every Wallet endpoint) and reject — with `HTTPException(403)` —
    any request where `client_id` does not match the authenticated
    caller's own identity, mirroring the WebSocket's `client_id` ==
    token-subject rule."""

    def test_returns_403_when_client_id_does_not_match_authenticated_user(
        self, client: TestClient
    ) -> None:
        """The core cross-user guarantee: Alice's valid token must
        never grant her access to a history request naming Bob's
        identity as `client_id`, even though the room itself is the
        same underlying resource either way."""
        alice_token = _register_and_login(client, email="alice-cross@example.com")
        _register_and_login(client, email="bob-cross@example.com")

        response = client.get(
            _history_url("bob-cross@example.com", room_id="room-shared"),
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    def test_returns_401_without_a_token(self, client: TestClient) -> None:
        response = client.get(
            _history_url("no-token@example.com", room_id="room-shared")
        )
        assert response.status_code in (401, 403)

    def test_returns_401_with_a_malformed_token(self, client: TestClient) -> None:
        response = client.get(
            _history_url("someone@example.com", room_id="room-shared"),
            headers=_auth_headers("not-a-real-jwt"),
        )
        assert response.status_code == 401

    def test_succeeds_when_client_id_matches_authenticated_user(
        self, client: TestClient
    ) -> None:
        """Sanity check that the ownership gate isn't over-broad: a
        caller requesting history *as themselves* must still succeed."""
        token = _register_and_login(client, email="carol-cross@example.com")

        response = client.get(
            _history_url("carol-cross@example.com", room_id="room-own"),
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "room_id": "room-own",
            "messages": [],
            "has_more": False,
        }
