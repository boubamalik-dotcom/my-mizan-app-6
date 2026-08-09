"""Tests for the clinic-queue real-time fan-out.

Two things are being defended here. The obvious one is that a change to
a queue reaches subscribers. The one that matters more is *what* the
frame contains: an earlier standalone implementation of this feature
streamed patient names and phone numbers to anyone who opened the
socket, so `TestTheFrameCarriesNoPatientInformation` asserts the
payload's whole shape rather than just spot-checking a field.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Mapping, Tuple

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.queue_controller import QueueController
from src.layer_2_api.main_router import api_router
from src.layer_2_api.realtime.queue_broadcaster import (
    EVENT_QUEUE_UPDATED,
    QueueBroadcaster,
    channel_for,
    queue_state_payload,
)
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_4_data_access.events.message_broker import (
    MessageBroker,
    MessageBrokerError,
)
from src.layer_4_data_access.repositories.queue_repository import ClinicQueueRecord
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"


class RecordingBroker(MessageBroker):
    """An in-memory `MessageBroker` that records what was published and
    can replay it to subscribers, so these tests need no Redis."""

    def __init__(self) -> None:
        self.published: List[Tuple[str, Mapping[str, Any]]] = []
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    async def connect(self) -> None:  # pragma: no cover - nothing to open
        return

    async def disconnect(self) -> None:  # pragma: no cover - nothing to close
        return

    async def publish(self, room_id: str, payload: Mapping[str, Any]) -> None:
        self.published.append((room_id, dict(payload)))
        for queue in self._queues.get(room_id, []):
            queue.put_nowait(dict(payload))

    def subscribe(self, room_id: str):
        queues = self._queues.setdefault(room_id, [])

        class _Subscription:
            async def __aenter__(_self) -> AsyncIterator[Mapping[str, Any]]:
                _self._queue: asyncio.Queue = asyncio.Queue()
                queues.append(_self._queue)

                async def _iterate() -> AsyncIterator[Mapping[str, Any]]:
                    while True:
                        yield await _self._queue.get()

                return _iterate()

            async def __aexit__(_self, *exc_info: object) -> None:
                queues.remove(_self._queue)

        return _Subscription()


class BrokenBroker(RecordingBroker):
    """A broker whose publishes always fail, standing in for Redis being
    down."""

    async def publish(self, room_id: str, payload: Mapping[str, Any]) -> None:
        raise MessageBrokerError("redis is down")


def _clinic_record(**overrides: Any) -> ClinicQueueRecord:
    defaults: Dict[str, Any] = {
        "id": "clinic-1",
        "name": "عيادة الأمل",
        "specialty": "طب عام",
        "district": "وهران",
        "service_rate_minutes": 8,
        "is_accepting_patients": True,
        "waiting_count": 3,
        "now_serving_ticket": 7,
    }
    defaults.update(overrides)
    return ClinicQueueRecord(**defaults)


class TestTheFrameCarriesNoPatientInformation:
    def test_the_payload_has_exactly_these_keys_and_no_others(self) -> None:
        # Asserted as an exact set, not a spot check: the failure being
        # guarded against is somebody *adding* a field — "just the
        # patient's name so the dashboard can show it" — and an
        # allow-list is the only assertion that catches that.
        payload = queue_state_payload(_clinic_record())

        assert set(payload) == {
            "event",
            "clinic_id",
            "waiting_count",
            "now_serving_ticket",
            "is_accepting_patients",
            "average_service_minutes",
            "estimated_wait_minutes",
        }

    def test_it_says_only_that_the_queue_moved(self) -> None:
        payload = queue_state_payload(_clinic_record())

        assert payload["event"] == EVENT_QUEUE_UPDATED
        assert payload["clinic_id"] == "clinic-1"
        assert payload["waiting_count"] == 3
        assert payload["now_serving_ticket"] == 7
        assert payload["estimated_wait_minutes"] == 24

    def test_an_idle_room_reports_no_ticket(self) -> None:
        payload = queue_state_payload(_clinic_record(now_serving_ticket=None))
        assert payload["now_serving_ticket"] is None


class TestChannelNaming:
    def test_queue_traffic_is_namespaced_away_from_chat_rooms(self) -> None:
        # Both features share one broker; a clinic id colliding with a
        # chat room name would cross the streams.
        assert channel_for("clinic-1") == "queue:clinic-1"

    def test_each_clinic_has_its_own_channel(self) -> None:
        assert channel_for("a") != channel_for("b")


class TestPublishingNeverBreaksTheWrite:
    async def test_a_broker_failure_is_swallowed(self) -> None:
        # The reservation is already committed by this point. Failing
        # the request because a *notification* failed would trade a
        # degraded feature for a broken one.
        broadcaster = QueueBroadcaster(broker=BrokenBroker())

        await broadcaster.publish_queue_state(_clinic_record())

    async def test_a_healthy_broker_publishes_to_the_clinics_channel(self) -> None:
        broker = RecordingBroker()
        broadcaster = QueueBroadcaster(broker=broker)

        await broadcaster.publish_queue_state(_clinic_record())

        assert len(broker.published) == 1
        channel, payload = broker.published[0]
        assert channel == "queue:clinic-1"
        assert payload["event"] == EVENT_QUEUE_UPDATED


# -- The endpoints announce their changes ---------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest.fixture
def broker() -> RecordingBroker:
    return RecordingBroker()


@pytest_asyncio.fixture
async def app(
    session_factory: async_sessionmaker, broker: RecordingBroker
) -> FastAPI:
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


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, *, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "T"},
    )
    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    return logged_in.json()["access_token"]


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def clinic_id(session_factory: async_sessionmaker) -> str:
    async with UnitOfWork(session_factory) as uow:
        clinic = await uow.queues.create_clinic(
            name="عيادة الأمل",
            specialty="طب عام",
            district="وهران",
            service_rate_minutes=8,
        )
        await uow.commit()
    return clinic.id


class TestEveryQueueChangeIsAnnounced:
    async def test_joining_announces_the_new_length(
        self, client: AsyncClient, broker: RecordingBroker, clinic_id: str
    ) -> None:
        token = await _login(client, email="patient@example.com")

        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
        )

        assert len(broker.published) == 1
        channel, payload = broker.published[-1]
        assert channel == channel_for(clinic_id)
        assert payload["waiting_count"] == 1

    async def test_cancelling_announces_the_shorter_queue(
        self, client: AsyncClient, broker: RecordingBroker, clinic_id: str
    ) -> None:
        token = await _login(client, email="patient@example.com")
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
            )
        ).json()["id"]

        await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}", headers=_auth(token)
        )

        assert broker.published[-1][1]["waiting_count"] == 0

    async def test_calling_the_next_patient_announces_the_new_ticket(
        self, client: AsyncClient, broker: RecordingBroker, clinic_id: str
    ) -> None:
        patient_token = await _login(client, email="patient@example.com")
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(patient_token)
        )
        admin_token = await _login(client, email="admin@example.com")

        await client.post(f"/api/v1/queues/{clinic_id}/next", headers=_auth(admin_token))

        payload = broker.published[-1][1]
        assert payload["now_serving_ticket"] == 1
        assert payload["waiting_count"] == 0

    async def test_an_idle_advance_announces_nothing(
        self, client: AsyncClient, broker: RecordingBroker, clinic_id: str
    ) -> None:
        # Telling subscribers the queue moved when it did not would make
        # every idle button press look like activity.
        admin_token = await _login(client, email="admin@example.com")

        await client.post(f"/api/v1/queues/{clinic_id}/next", headers=_auth(admin_token))

        assert broker.published == []

    async def test_a_refused_join_announces_nothing(
        self, client: AsyncClient, broker: RecordingBroker, clinic_id: str
    ) -> None:
        # Nothing was written, so there is nothing to announce.
        token = await _login(client, email="patient@example.com")
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
        )
        broker.published.clear()

        duplicate = await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
        )

        assert duplicate.status_code == 409
        assert broker.published == []

    async def test_a_broker_outage_does_not_fail_the_reservation(
        self, session_factory: async_sessionmaker, clinic_id: str
    ) -> None:
        application = FastAPI()
        application.include_router(api_router, prefix="/api/v1")

        def unit_of_work_factory() -> UnitOfWork:
            return UnitOfWork(session_factory)

        application.state.queue_controller = QueueController(
            unit_of_work_factory=unit_of_work_factory,
            broadcaster=QueueBroadcaster(broker=BrokenBroker()),
        )
        application.state.auth_controller = AuthController(
            auth_service=AuthService(secret_key=TEST_SECRET_KEY),
            unit_of_work_factory=unit_of_work_factory,
        )
        transport = ASGITransport(app=application)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            token = await _login(ac, email="patient@example.com")

            response = await ac.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
            )

        assert response.status_code == 201, response.text

    async def test_a_controller_without_a_broadcaster_still_works(
        self, session_factory: async_sessionmaker, clinic_id: str
    ) -> None:
        # Real-time is additive: a deployment with no Redis must still
        # be able to take a reservation.
        application = FastAPI()
        application.include_router(api_router, prefix="/api/v1")

        def unit_of_work_factory() -> UnitOfWork:
            return UnitOfWork(session_factory)

        application.state.queue_controller = QueueController(
            unit_of_work_factory=unit_of_work_factory
        )
        application.state.auth_controller = AuthController(
            auth_service=AuthService(secret_key=TEST_SECRET_KEY),
            unit_of_work_factory=unit_of_work_factory,
        )
        transport = ASGITransport(app=application)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            token = await _login(ac, email="patient@example.com")
            response = await ac.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth(token)
            )

        assert response.status_code == 201, response.text
