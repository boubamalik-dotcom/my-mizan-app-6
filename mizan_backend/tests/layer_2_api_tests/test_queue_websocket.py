"""End-to-end tests for the clinic-queue WebSocket endpoint.

Uses the synchronous `TestClient`, which is what supports
`websocket_connect`, in its own module so the async `httpx` tests
elsewhere keep their own event loop. Mirrors
`test_chat_routes.py`'s arrangement for the same reason.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.queue_controller import QueueController
from src.layer_2_api.main_router import api_router
from src.layer_2_api.realtime.queue_broadcaster import QueueBroadcaster
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_4_data_access.events.message_broker import MessageBroker
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"


class LoopbackBroker(MessageBroker):
    """Publishes straight back to this process's subscribers.

    Enough to prove the socket path end to end without a Redis server;
    the cross-process half is `RedisMessageBroker`'s own responsibility
    and is covered by the chat engine's broker tests.
    """

    def __init__(self) -> None:
        import asyncio

        self._asyncio = asyncio
        self._queues: Dict[str, List[Any]] = {}
        self.published: List[Tuple[str, Mapping[str, Any]]] = []

    async def connect(self) -> None:
        return

    async def disconnect(self) -> None:
        return

    async def publish(self, room_id: str, payload: Mapping[str, Any]) -> None:
        self.published.append((room_id, dict(payload)))
        for queue in self._queues.get(room_id, []):
            queue.put_nowait(dict(payload))

    def subscribe(self, room_id: str):
        outer = self

        class _Subscription:
            async def __aenter__(self_inner):
                self_inner._queue = outer._asyncio.Queue()
                outer._queues.setdefault(room_id, []).append(self_inner._queue)

                async def _iterate():
                    while True:
                        yield await self_inner._queue.get()

                return _iterate()

            async def __aexit__(self_inner, *exc_info: object) -> None:
                outer._queues[room_id].remove(self_inner._queue)

        return _Subscription()


@pytest.fixture
def session_factory() -> async_sessionmaker:
    # A file-backed SQLite database rather than `:memory:`: `TestClient`
    # drives the app on its own event loop and opens several
    # connections, which an in-memory database would not share.
    import tempfile
    from pathlib import Path

    directory = tempfile.mkdtemp()
    path = Path(directory) / "queue_ws_test.db"
    engine = build_engine(f"sqlite+aiosqlite:///{path}")

    import asyncio

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    return build_session_factory(build_engine(f"sqlite+aiosqlite:///{path}"))


@pytest.fixture
def broker() -> LoopbackBroker:
    return LoopbackBroker()


@pytest.fixture
def app(session_factory: async_sessionmaker, broker: LoopbackBroker) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    broadcaster = QueueBroadcaster(broker=broker)
    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.queue_controller = QueueController(
        unit_of_work_factory=unit_of_work_factory, broadcaster=broadcaster
    )
    application.state.queue_broadcaster = broadcaster
    application.state.auth_controller = AuthController(
        auth_service=AuthService(secret_key=TEST_SECRET_KEY),
        unit_of_work_factory=unit_of_work_factory,
        bootstrap_admin_emails=["admin@example.com"],
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, *, email: str) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "T"},
    )
    logged_in = client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    return logged_in.json()["access_token"]


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _clinic(client: TestClient, token: str) -> str:
    """Registers a clinic through the seed path and returns its id."""
    import asyncio

    from src.layer_5_storage.db_config import build_session_factory  # noqa: F401

    # Created through the API's own read afterwards; the seed itself has
    # no endpoint, so it goes in via the repository.
    factory = client.app.state.queue_controller._unit_of_work_factory

    async def _create() -> str:
        async with factory() as uow:
            clinic = await uow.queues.create_clinic(
                name="عيادة الأمل",
                specialty="طب عام",
                district="وهران",
                service_rate_minutes=8,
            )
            await uow.commit()
        return clinic.id

    return asyncio.run(_create())


class TestAuthentication:
    def test_a_socket_without_a_token_is_refused(self, client: TestClient) -> None:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/queues/ws/clinic-1"):
                pass

    def test_a_socket_with_a_rubbish_token_is_refused(
        self, client: TestClient
    ) -> None:
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/api/v1/queues/ws/clinic-1?token=not-a-real-token"
            ):
                pass

    def test_a_valid_token_is_accepted(self, client: TestClient) -> None:
        token = _login(client, email="patient@example.com")

        with client.websocket_connect(f"/api/v1/queues/ws/clinic-1?token={token}"):
            pass


class TestLiveDelivery:
    def test_a_join_reaches_a_subscribed_socket(self, client: TestClient) -> None:
        token = _login(client, email="patient@example.com")
        other = _login(client, email="watcher@example.com")
        clinic_id = _clinic(client, token)

        with client.websocket_connect(
            f"/api/v1/queues/ws/{clinic_id}?token={other}"
        ) as socket:
            client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
            )

            frame = socket.receive_json()

        assert frame["event"] == "queue_updated"
        assert frame["clinic_id"] == clinic_id
        assert frame["waiting_count"] == 1

    def test_calling_the_next_patient_reaches_the_socket(
        self, client: TestClient
    ) -> None:
        token = _login(client, email="patient@example.com")
        admin = _login(client, email="admin@example.com")
        clinic_id = _clinic(client, token)
        client.post(f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token))

        with client.websocket_connect(
            f"/api/v1/queues/ws/{clinic_id}?token={token}"
        ) as socket:
            client.post(f"/api/v1/queues/{clinic_id}/next", headers=_auth(admin))

            frame = socket.receive_json()

        assert frame["now_serving_ticket"] == 1
        assert frame["waiting_count"] == 0

    def test_the_frame_names_no_patient(self, client: TestClient) -> None:
        # The constraint that matters. Asserted on a real frame off a
        # real socket, not just on the payload builder.
        token = _login(client, email="patient@example.com")
        clinic_id = _clinic(client, token)

        with client.websocket_connect(
            f"/api/v1/queues/ws/{clinic_id}?token={token}"
        ) as socket:
            client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
            )
            frame = socket.receive_json()

        assert set(frame) == {
            "event",
            "clinic_id",
            "waiting_count",
            "now_serving_ticket",
            "is_accepting_patients",
            "average_service_minutes",
            "estimated_wait_minutes",
        }
        assert "patient@example.com" not in str(frame)

    def test_a_socket_hears_nothing_about_another_clinic(
        self, client: TestClient
    ) -> None:
        token = _login(client, email="patient@example.com")
        watched = _clinic(client, token)
        other = _clinic(client, token)

        with client.websocket_connect(
            f"/api/v1/queues/ws/{watched}?token={token}"
        ) as socket:
            client.post(f"/api/v1/queues/{other}/reservations", headers=_auth(token))
            # Then something on the watched clinic, so the assertion is
            # "the first frame is ours" rather than a timeout.
            client.post(f"/api/v1/queues/{watched}/reservations", headers=_auth(token))

            frame = socket.receive_json()

        assert frame["clinic_id"] == watched
