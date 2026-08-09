"""End-to-end tests for Mizan Door's Layer 2 HTTP routes.

Covers the wire contract `mizan_frontend`'s Mizan Door mini-program
already parses, the optional authentication on `GET /queues`, and the
ownership rule on cancellation.

Uses `httpx.AsyncClient` over `ASGITransport` inside fully async test
functions, matching `test_wallet_routes.py`, so the app, its
controllers/`UnitOfWork`, and every request share one event loop.
"""
from __future__ import annotations

from typing import AsyncIterator, Dict, Tuple

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.audit.audit_controller import AuditController
from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.queue_controller import QueueController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.audit.audit_service import AuditService
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"
#: Promoted to admin at registration by the auth controller, which is
#: how a test gets an account able to grant roles.
BOOTSTRAP_ADMIN = "admin@example.com"


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


@pytest_asyncio.fixture
async def app(session_factory: async_sessionmaker) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.queue_controller = QueueController(
        unit_of_work_factory=unit_of_work_factory
    )
    application.state.auth_controller = AuthController(
        auth_service=AuthService(secret_key=TEST_SECRET_KEY),
        unit_of_work_factory=unit_of_work_factory,
        bootstrap_admin_emails=[BOOTSTRAP_ADMIN],
    )
    # Role administration lives on the audit router, which is how a
    # test promotes an account to `clinic_staff`.
    application.state.audit_controller = AuditController(
        audit_service=AuditService(),
        unit_of_work_factory=unit_of_work_factory,
    )
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _register_and_login(client: AsyncClient, *, email: str) -> Tuple[str, str]:
    """Registers a new user and logs in, returning `(user_id, access_token)`."""
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test Patient"},
    )
    assert register_response.status_code == 201, register_response.text
    user_id = register_response.json()["id"]

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert login_response.status_code == 200, login_response.text
    return user_id, login_response.json()["access_token"]


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _admin(client: AsyncClient) -> str:
    """The bootstrap admin's token."""
    _, token = await _register_and_login(client, email=BOOTSTRAP_ADMIN)
    return token


async def _with_role(client: AsyncClient, *, email: str, role: str) -> str:
    """Registers a user, has the admin grant them `role`, and returns a
    token that carries it.

    The token is fetched *after* the promotion because roles are
    resolved per request from the account, not baked into the token —
    but logging in again also proves the promotion actually persisted
    rather than only appearing in the promoting admin's response.
    """
    user_id, _ = await _register_and_login(client, email=email)
    admin_token = await _admin(client)

    promoted = await client.patch(
        f"/api/v1/audit/users/{user_id}/role",
        json={"role": role},
        headers=_auth_headers(admin_token),
    )
    assert promoted.status_code == 200, promoted.text

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    return logged_in.json()["access_token"]


async def _staff(client: AsyncClient, *, email: str = "reception@example.com") -> str:
    """A `clinic_staff` token — the role that may call patients."""
    return await _with_role(client, email=email, role="clinic_staff")


async def _create_clinic(
    session_factory: async_sessionmaker,
    *,
    name: str = "عيادة الأمل للطب العام",
    specialty: str = "طب عام",
    district: str = "حي الصباح، وهران",
    service_rate_minutes: int = 8,
    is_accepting_patients: bool = True,
) -> str:
    async with UnitOfWork(session_factory) as uow:
        clinic = await uow.queues.create_clinic(
            name=name,
            specialty=specialty,
            district=district,
            service_rate_minutes=service_rate_minutes,
            is_accepting_patients=is_accepting_patients,
        )
        await uow.commit()
    return clinic.id


@pytest_asyncio.fixture
async def clinic_id(session_factory: async_sessionmaker) -> str:
    return await _create_clinic(session_factory)


@pytest_asyncio.fixture
async def patient(client: AsyncClient) -> Tuple[str, str]:
    return await _register_and_login(client, email="patient@example.com")


@pytest_asyncio.fixture
async def other_patient(client: AsyncClient) -> Tuple[str, str]:
    return await _register_and_login(client, email="other@example.com")


class TestListingQueues:
    async def test_is_readable_without_signing_in(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # A patient deciding whether it is worth leaving the house
        # should not have to sign in first.
        response = await client.get("/api/v1/queues")

        assert response.status_code == 200, response.text
        assert len(response.json()["queues"]) == 1

    async def test_an_anonymous_caller_gets_no_reservation(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # There is nobody to attribute one to.
        response = await client.get("/api/v1/queues")
        assert response.json()["reservation"] is None

    async def test_returns_the_shape_the_frontend_parses(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # Guards the contract in `queue_model.dart`: a rename here is a
        # silently broken screen there.
        queue = (await client.get("/api/v1/queues")).json()["queues"][0]

        assert queue["clinic"]["name"] == "عيادة الأمل للطب العام"
        assert queue["clinic"]["specialty"] == "طب عام"
        assert queue["clinic"]["district"] == "حي الصباح، وهران"
        assert queue["waiting_count"] == 0
        assert queue["average_service_minutes"] == 8
        assert queue["is_accepting_patients"] is True

    async def test_reports_a_growing_queue(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        for _, token in (patient, other_patient):
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )

        queue = (await client.get("/api/v1/queues")).json()["queues"][0]

        assert queue["waiting_count"] == 2
        assert queue["estimated_wait_minutes"] == 16

    async def test_a_signed_in_caller_sees_their_own_place(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        body = (await client.get("/api/v1/queues", headers=_auth_headers(token))).json()

        assert body["reservation"] is not None
        assert body["reservation"]["clinic_id"] == clinic_id

    async def test_one_patient_never_sees_anothers_place(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        _, token = patient
        _, other_token = other_patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        body = (
            await client.get("/api/v1/queues", headers=_auth_headers(other_token))
        ).json()

        assert body["reservation"] is None

    async def test_a_rubbish_token_degrades_to_the_public_view(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # Rather than locking the caller out of a page that does not
        # require them to be anyone in particular.
        response = await client.get(
            "/api/v1/queues", headers=_auth_headers("not-a-real-token")
        )

        assert response.status_code == 200
        assert response.json()["reservation"] is None

    async def test_an_empty_list_is_a_legitimate_answer(
        self, client: AsyncClient
    ) -> None:
        # No clinics registered: the frontend renders "no active
        # queues", which is not an error state.
        response = await client.get("/api/v1/queues")

        assert response.status_code == 200
        assert response.json()["queues"] == []


class TestJoiningAQueue:
    async def test_requires_authentication(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # A reservation belongs to a person.
        response = await client.post(f"/api/v1/queues/{clinic_id}/reservations")
        assert response.status_code == 401

    async def test_issues_the_first_ticket(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, token = patient

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["ticket_number"] == 1
        assert body["position"] == 0
        assert body["status"] == "waiting"

    async def test_position_counts_people_ahead_not_the_ticket(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        # The two numbers differ, and the frontend renders `position`.
        _, first_token = patient
        _, second_token = other_patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(first_token),
        )

        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(second_token),
            )
        ).json()

        assert body["ticket_number"] == 2
        assert body["position"] == 1

    async def test_returns_the_shape_the_frontend_parses(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # Guards the contract in `reservation_model.dart`.
        _, token = patient
        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()

        for field in (
            "id",
            "clinic_id",
            "clinic_name",
            "position",
            "estimated_wait_minutes",
            "joined_at",
        ):
            assert field in body, f"missing `{field}`"

    async def test_estimates_the_wait_from_the_clinics_own_pace(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        dentist = await _create_clinic(
            session_factory, name="مركز النور", service_rate_minutes=15
        )
        _, first_token = patient
        _, second_token = other_patient
        await client.post(
            f"/api/v1/queues/{dentist}/reservations", headers=_auth_headers(first_token)
        )

        body = (
            await client.post(
                f"/api/v1/queues/{dentist}/reservations",
                headers=_auth_headers(second_token),
            )
        ).json()

        assert body["estimated_wait_minutes"] == 15

    async def test_joining_twice_conflicts(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # 409 is what the frontend maps to "لديك دور محجوز بالفعل".
        _, token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        assert response.status_code == 409, response.text

    async def test_a_closed_clinic_is_unprocessable(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker,
        patient: Tuple[str, str],
    ) -> None:
        # 422 is what the frontend maps to "لا تستقبل حجوزات حالياً".
        closed = await _create_clinic(
            session_factory, name="مركز الحياة", is_accepting_patients=False
        )
        _, token = patient

        response = await client.post(
            f"/api/v1/queues/{closed}/reservations", headers=_auth_headers(token)
        )

        assert response.status_code == 422, response.text

    async def test_an_unknown_clinic_is_not_found(
        self, client: AsyncClient, patient: Tuple[str, str]
    ) -> None:
        _, token = patient

        response = await client.post(
            "/api/v1/queues/no-such-clinic/reservations", headers=_auth_headers(token)
        )

        assert response.status_code == 404


class TestCancelling:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/queues/reservations/whatever")
        assert response.status_code == 401

    async def test_gives_up_the_callers_own_place(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, token = patient
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()["id"]

        response = await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelled"

    async def test_the_queue_shortens_afterwards(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, token = patient
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()["id"]
        await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(token),
        )

        queue = (await client.get("/api/v1/queues")).json()["queues"][0]

        assert queue["waiting_count"] == 0

    async def test_one_patient_cannot_cancel_anothers_place(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        _, token = patient
        _, other_token = other_patient
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()["id"]

        response = await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(other_token),
        )

        assert response.status_code == 403

    async def test_a_refused_cancellation_leaves_the_place_intact(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        # The 403 must be a refusal, not a failed-but-partial write.
        _, token = patient
        _, other_token = other_patient
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()["id"]

        await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(other_token),
        )

        body = (await client.get("/api/v1/queues", headers=_auth_headers(token))).json()
        assert body["reservation"]["id"] == reservation_id
        assert body["reservation"]["status"] == "waiting"

    async def test_cancelling_twice_is_gone(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # 410 is what the frontend maps to "انتهت صلاحية هذا الحجز".
        _, token = patient
        reservation_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        ).json()["id"]
        await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(token),
        )

        response = await client.delete(
            f"/api/v1/queues/reservations/{reservation_id}",
            headers=_auth_headers(token),
        )

        assert response.status_code == 410

    async def test_an_unknown_reservation_is_not_found(
        self, client: AsyncClient, patient: Tuple[str, str]
    ) -> None:
        _, token = patient

        response = await client.delete(
            "/api/v1/queues/reservations/no-such-reservation",
            headers=_auth_headers(token),
        )

        assert response.status_code == 404


class TestCallingTheNextPatient:
    async def test_requires_authentication(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        response = await client.post(f"/api/v1/queues/{clinic_id}/next")
        assert response.status_code == 401

    async def test_an_ordinary_patient_may_not_advance_the_queue(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # The rule the whole permission exists for: someone standing in
        # the queue who could advance it could serve themselves to the
        # front of it.
        _, token = patient

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(token)
        )

        assert response.status_code == 403

    async def test_a_refused_call_does_not_move_the_queue(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # The 403 must be a refusal, not a failed-but-partial advance.
        _, token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
        )

        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(token)
        )

        queue = (await client.get("/api/v1/queues")).json()["queues"][0]
        assert queue["waiting_count"] == 1
        assert queue["now_serving_ticket"] is None

    async def test_an_auditor_may_not_advance_the_queue(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # Auditors are read-only by design; calling a patient is a
        # write, so the read-only guarantee has to hold here too.
        token = await _with_role(client, email="auditor@example.com", role="auditor")

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(token)
        )

        assert response.status_code == 403

    async def test_clinic_staff_may_advance_the_queue(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, patient_token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )
        staff_token = await _staff(client)

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )

        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "called_next"

    async def test_an_admin_may_advance_the_queue(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        admin_token = await _admin(client)

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(admin_token)
        )

        assert response.status_code == 200, response.text

    async def test_moves_the_patient_from_waiting_to_in_consultation(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, patient_token = patient
        joined = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(patient_token),
            )
        ).json()
        assert joined["status"] == "waiting"
        staff_token = await _staff(client)

        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )
        ).json()

        assert body["now_serving"]["id"] == joined["id"]
        assert body["now_serving"]["status"] == "in_consultation"
        assert body["completed"] is None

    async def test_marks_the_previous_patient_as_served(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        _, first_token = patient
        _, second_token = other_patient
        first = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(first_token),
            )
        ).json()
        second = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(second_token),
            )
        ).json()
        staff_token = await _staff(client)

        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )
        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )
        ).json()

        assert body["completed"]["id"] == first["id"]
        assert body["completed"]["status"] == "served"
        assert body["now_serving"]["id"] == second["id"]

    async def test_returns_the_updated_queue_state(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        for _, token in (patient, other_patient):
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        staff_token = await _staff(client)

        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )
        ).json()

        # One called in, one still to come.
        assert body["queue"]["waiting_count"] == 1
        assert body["queue"]["now_serving_ticket"] == 1

    async def test_an_empty_queue_is_reported_not_refused(
        self, client: AsyncClient, clinic_id: str
    ) -> None:
        # Pressing the button on an empty queue is not a mistake, so it
        # must not answer with an error.
        staff_token = await _staff(client)

        response = await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "queue_empty"
        assert (body["now_serving"], body["completed"]) == (None, None)

    async def test_finishing_the_last_patient_is_distinguishable(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, patient_token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )
        staff_token = await _staff(client)
        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )

        body = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )
        ).json()

        assert body["outcome"] == "completed_last"
        assert body["completed"] is not None
        assert body["now_serving"] is None

    async def test_an_unknown_clinic_is_not_found(self, client: AsyncClient) -> None:
        staff_token = await _staff(client)

        response = await client.post(
            "/api/v1/queues/no-such-clinic/next", headers=_auth_headers(staff_token)
        )

        assert response.status_code == 404

    async def test_the_queue_drains_instead_of_growing_forever(
        self, client: AsyncClient, session_factory: async_sessionmaker, clinic_id: str
    ) -> None:
        # The gap this feature closes: before it, a reservation could
        # only be created or cancelled, so a queue never shrank through
        # normal use.
        tokens = [
            (await _register_and_login(client, email=f"drain{i}@example.com"))[1]
            for i in range(3)
        ]
        for token in tokens:
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations", headers=_auth_headers(token)
            )
        assert (await client.get("/api/v1/queues")).json()["queues"][0][
            "waiting_count"
        ] == 3

        staff_token = await _staff(client)
        for _ in range(4):
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )

        queue = (await client.get("/api/v1/queues")).json()["queues"][0]
        assert queue["waiting_count"] == 0
        assert queue["now_serving_ticket"] is None


class TestWhatThePatientSeesWhenCalled:
    async def test_their_own_place_reports_the_consultation(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, patient_token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )
        staff_token = await _staff(client)
        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )

        mine = (
            await client.get("/api/v1/queues", headers=_auth_headers(patient_token))
        ).json()["reservation"]

        assert mine is not None
        assert mine["status"] == "in_consultation"
        assert mine["position"] == 0

    async def test_a_served_patient_no_longer_holds_a_place(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        _, patient_token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )
        staff_token = await _staff(client)
        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )
        await client.post(
            f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
        )

        body = (
            await client.get("/api/v1/queues", headers=_auth_headers(patient_token))
        ).json()

        assert body["reservation"] is None

    async def test_a_served_patient_may_join_again(
        self, client: AsyncClient, clinic_id: str, patient: Tuple[str, str]
    ) -> None:
        # A follow-up visit later the same day is legitimate.
        _, patient_token = patient
        await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )
        staff_token = await _staff(client)
        for _ in range(2):
            await client.post(
                f"/api/v1/queues/{clinic_id}/next", headers=_auth_headers(staff_token)
            )

        again = await client.post(
            f"/api/v1/queues/{clinic_id}/reservations",
            headers=_auth_headers(patient_token),
        )

        assert again.status_code == 201, again.text
        assert again.json()["ticket_number"] == 2


class TestTheQueueMovesWithoutRewritingTickets:
    async def test_a_patient_advances_when_the_one_ahead_leaves(
        self,
        client: AsyncClient,
        clinic_id: str,
        patient: Tuple[str, str],
        other_patient: Tuple[str, str],
    ) -> None:
        _, first_token = patient
        _, second_token = other_patient
        ahead_id = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(first_token),
            )
        ).json()["id"]
        mine = (
            await client.post(
                f"/api/v1/queues/{clinic_id}/reservations",
                headers=_auth_headers(second_token),
            )
        ).json()
        assert mine["position"] == 1

        await client.delete(
            f"/api/v1/queues/reservations/{ahead_id}",
            headers=_auth_headers(first_token),
        )

        refreshed = (
            await client.get("/api/v1/queues", headers=_auth_headers(second_token))
        ).json()["reservation"]

        assert refreshed["position"] == 0
        # Nothing was rewritten: the ticket is the one they were given.
        assert refreshed["ticket_number"] == mine["ticket_number"]


class TestOpenApiDocumentation:
    @pytest.mark.parametrize(
        ("path", "method"),
        [
            ("/api/v1/queues", "get"),
            ("/api/v1/queues/{clinic_id}/reservations", "post"),
            ("/api/v1/queues/reservations/{reservation_id}", "delete"),
        ],
    )
    async def test_every_endpoint_is_documented(
        self, client: AsyncClient, path: str, method: str
    ) -> None:
        schema = (await client.get("/openapi.json")).json()
        assert method in schema["paths"][path]

    async def test_the_write_endpoints_advertise_the_bearer_scheme(
        self, client: AsyncClient
    ) -> None:
        # Only asserted for the writes. FastAPI marks `GET /queues` with
        # the same `HTTPBearer` requirement even though its scheme is
        # `auto_error=False`, because OpenAPI has no way to say "a token
        # is read if present but not required" — so the schema cannot
        # distinguish the two, and the real contract for that endpoint
        # is behavioural (see `test_is_readable_without_signing_in`).
        schema = (await client.get("/openapi.json")).json()

        for path, method in (
            ("/api/v1/queues/{clinic_id}/reservations", "post"),
            ("/api/v1/queues/reservations/{reservation_id}", "delete"),
        ):
            assert schema["paths"][path][method]["security"] == [{"HTTPBearer": []}]
