"""Functional tests for `QueueRepository` against a real (in-memory
SQLite) database.

These cover the repository's *behaviour*: ticket assignment, derived
queue positions, and the rules it enforces. Genuine **concurrent**
ticket assignment — many independent connections racing to join the
same clinic — is covered separately against a real Postgres server in
`tests/integration_tests/test_queue_concurrency.py`, because SQLite
funnels every `:memory:` connection through one connection and ignores
``SELECT ... FOR UPDATE`` entirely, so it cannot exercise the lock this
repository depends on.
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_3_business.queue.exceptions import (
    AlreadyInQueueError,
    ClinicNotAcceptingPatientsError,
    ReservationNotActiveError,
)
from src.layer_4_data_access.repositories.queue_repository import (
    AdvanceOutcome,
    ClinicNotFoundError,
    QueueRepository,
    ReservationNotFoundError,
    ReservationStatus,
)
from src.layer_4_data_access.repositories.user_repository import UserRepository
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = build_session_factory(engine)
    async with factory() as open_session:
        yield open_session

    await engine.dispose()


@pytest.fixture
def repository(session: AsyncSession) -> QueueRepository:
    return QueueRepository(session)


@pytest_asyncio.fixture
async def patient_id(session: AsyncSession) -> str:
    """`queue_reservations.user_id` is a real foreign key, so a
    reservation needs a real account behind it."""
    user = await UserRepository(session).create_user(
        email="patient@example.com", hashed_password="hashed", full_name="Patient"
    )
    await session.flush()
    return user.id


@pytest_asyncio.fixture
async def other_patient_id(session: AsyncSession) -> str:
    user = await UserRepository(session).create_user(
        email="other@example.com", hashed_password="hashed", full_name="Other"
    )
    await session.flush()
    return user.id


@pytest_asyncio.fixture
async def clinic_id(repository: QueueRepository) -> str:
    clinic = await repository.create_clinic(
        name="عيادة الأمل",
        specialty="طب عام",
        district="وهران",
        service_rate_minutes=8,
    )
    return clinic.id


class TestListingQueues:
    async def test_a_clinic_with_no_reservations_still_appears(
        self, repository: QueueRepository, clinic_id: str
    ) -> None:
        # With the status filter in WHERE instead of the JOIN's ON
        # clause, an empty clinic would vanish from the list entirely.
        queues = await repository.get_clinics_with_queue_status()

        assert [queue.id for queue in queues] == [clinic_id]
        assert queues[0].waiting_count == 0

    async def test_counts_only_active_reservations(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.join_queue(clinic_id=clinic_id, user_id=other_patient_id)
        await repository.cancel_reservation(first.id)

        queues = await repository.get_clinics_with_queue_status()

        assert queues[0].waiting_count == 1

    async def test_a_cancelled_only_clinic_reports_an_empty_queue(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        await repository.cancel_reservation(reservation.id)

        queues = await repository.get_clinics_with_queue_status()

        assert len(queues) == 1
        assert queues[0].waiting_count == 0

    async def test_orders_clinics_by_name_for_a_stable_list(
        self, repository: QueueRepository
    ) -> None:
        # Otherwise the list reshuffles on every refresh.
        for name in ("جيم", "ألف", "باء"):
            await repository.create_clinic(
                name=name, specialty="طب عام", district="وهران", service_rate_minutes=5
            )

        queues = await repository.get_clinics_with_queue_status()

        assert [queue.name for queue in queues] == sorted(
            queue.name for queue in queues
        )

    async def test_carries_the_clinics_own_service_rate(
        self, repository: QueueRepository, clinic_id: str
    ) -> None:
        queues = await repository.get_clinics_with_queue_status()
        assert queues[0].service_rate_minutes == 8

    async def test_counts_each_clinics_queue_separately(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
    ) -> None:
        quiet = await repository.create_clinic(
            name="زاي", specialty="طب عام", district="وهران", service_rate_minutes=5
        )
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        queues = {queue.id: queue.waiting_count for queue in
                  await repository.get_clinics_with_queue_status()}

        assert queues[clinic_id] == 1
        assert queues[quiet.id] == 0


class TestJoiningAQueue:
    async def test_the_first_patient_receives_ticket_one(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )

        assert reservation.ticket_number == 1
        assert reservation.status is ReservationStatus.WAITING

    async def test_tickets_are_sequential(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        second = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )

        assert (first.ticket_number, second.ticket_number) == (1, 2)

    async def test_the_first_patient_has_nobody_ahead(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )

        assert reservation.people_ahead == 0
        assert reservation.estimated_wait_minutes == 0

    async def test_the_second_patient_waits_for_the_first(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        second = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )

        assert second.people_ahead == 1
        # One person ahead at this clinic's eight minutes per patient.
        assert second.estimated_wait_minutes == 8

    async def test_tickets_are_numbered_per_clinic_not_globally(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        other_clinic = await repository.create_clinic(
            name="مركز النور",
            specialty="طب الأسنان",
            district="وهران",
            service_rate_minutes=15,
        )
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        elsewhere = await repository.join_queue(
            clinic_id=other_clinic.id, user_id=patient_id
        )

        # Same patient, different clinic: their own ticket 1, not 2.
        assert elsewhere.ticket_number == 1

    async def test_a_patient_may_queue_at_two_different_clinics(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        # Legitimate: the one-place rule is per clinic, not per person.
        other_clinic = await repository.create_clinic(
            name="مركز النور", specialty="طب الأسنان", district="وهران",
            service_rate_minutes=15,
        )
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.join_queue(clinic_id=other_clinic.id, user_id=patient_id)

    async def test_a_patient_may_not_hold_two_places_in_one_clinic(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        with pytest.raises(AlreadyInQueueError):
            await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

    async def test_a_patient_may_rejoin_after_cancelling(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.cancel_reservation(first.id)

        rejoined = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )

        # A fresh ticket at the back, not the one they gave up.
        assert rejoined.ticket_number == 2

    async def test_a_closed_clinic_refuses(
        self, repository: QueueRepository, patient_id: str
    ) -> None:
        closed = await repository.create_clinic(
            name="مركز الحياة",
            specialty="الأمراض الجلدية",
            district="وهران",
            service_rate_minutes=12,
            is_accepting_patients=False,
        )

        with pytest.raises(ClinicNotAcceptingPatientsError):
            await repository.join_queue(clinic_id=closed.id, user_id=patient_id)

    async def test_an_unknown_clinic_is_reported_as_such(
        self, repository: QueueRepository, patient_id: str
    ) -> None:
        with pytest.raises(ClinicNotFoundError):
            await repository.join_queue(clinic_id="no-such-clinic", user_id=patient_id)

    async def test_carries_the_clinic_name_for_display(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        assert reservation.clinic_name == "عيادة الأمل"


class TestDerivedQueuePosition:
    async def test_the_position_moves_up_when_someone_ahead_cancels(
        self,
        repository: QueueRepository,
        session: AsyncSession,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        # The whole reason the stored ticket and the displayed position
        # are different numbers: nothing is rewritten here, yet the
        # answer changes.
        ahead = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        mine = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )
        assert mine.people_ahead == 1

        await repository.cancel_reservation(ahead.id)
        refreshed = await repository.get_reservation_by_id(mine.id)

        assert refreshed is not None
        assert refreshed.people_ahead == 0
        # The ticket itself never changed.
        assert refreshed.ticket_number == mine.ticket_number

    async def test_a_cancelled_reservation_reports_no_position_or_wait(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        cancelled = await repository.cancel_reservation(reservation.id)

        assert cancelled.people_ahead == 0
        assert cancelled.estimated_wait_minutes == 0

    async def test_the_wait_estimate_matches_the_position_shown_beside_it(
        self,
        repository: QueueRepository,
        session: AsyncSession,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        mine = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )

        assert mine.estimated_wait_minutes == mine.people_ahead * 8


class TestFindingTheCallersOwnPlace:
    async def test_returns_none_when_they_hold_none(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        assert await repository.get_active_reservation_for_user(patient_id) is None

    async def test_finds_an_active_place(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )

        found = await repository.get_active_reservation_for_user(patient_id)

        assert found is not None and found.id == reservation.id

    async def test_ignores_a_cancelled_place(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        await repository.cancel_reservation(reservation.id)

        assert await repository.get_active_reservation_for_user(patient_id) is None

    async def test_never_returns_another_patients_place(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        assert (
            await repository.get_active_reservation_for_user(other_patient_id) is None
        )


class TestCancelling:
    async def test_marks_the_reservation_cancelled(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )

        cancelled = await repository.cancel_reservation(reservation.id)

        assert cancelled.status is ReservationStatus.CANCELLED

    async def test_keeps_the_row_so_the_ticket_is_never_reissued(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        await repository.cancel_reservation(reservation.id)

        still_there = await repository.get_reservation_by_id(reservation.id)

        assert still_there is not None
        assert still_there.ticket_number == reservation.ticket_number

    async def test_cancelling_twice_is_refused(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        await repository.cancel_reservation(reservation.id)

        with pytest.raises(ReservationNotActiveError):
            await repository.cancel_reservation(reservation.id)

    async def test_an_unknown_reservation_is_reported_as_such(
        self, repository: QueueRepository
    ) -> None:
        with pytest.raises(ReservationNotFoundError):
            await repository.cancel_reservation("no-such-reservation")


class TestAdvancingTheQueue:
    async def test_calls_the_lowest_outstanding_ticket(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.join_queue(clinic_id=clinic_id, user_id=other_patient_id)

        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.outcome is AdvanceOutcome.CALLED_NEXT
        assert advance.now_serving is not None
        assert advance.now_serving.id == first.id
        assert advance.now_serving.status is ReservationStatus.IN_CONSULTATION

    async def test_the_first_call_completes_nobody(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.completed is None

    async def test_the_next_call_serves_the_patient_in_the_room(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        second = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )
        await repository.advance_clinic_queue(clinic_id)

        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.completed is not None
        assert advance.completed.id == first.id
        assert advance.completed.status is ReservationStatus.SERVED
        assert advance.now_serving is not None
        assert advance.now_serving.id == second.id

    async def test_records_when_the_patient_was_called_and_completed(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        called = (await repository.advance_clinic_queue(clinic_id)).now_serving
        assert called is not None and called.called_at is not None
        assert called.completed_at is None

        served = (await repository.advance_clinic_queue(clinic_id)).completed
        assert served is not None and served.completed_at is not None
        # The pair is what makes a consultation's duration measurable.
        assert served.called_at is not None
        assert served.completed_at >= served.called_at

    async def test_finishing_the_last_patient_empties_the_queue(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.advance_clinic_queue(clinic_id)

        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.outcome is AdvanceOutcome.COMPLETED_LAST
        assert advance.now_serving is None
        assert advance.completed is not None
        assert advance.queue.waiting_count == 0
        assert advance.queue.now_serving_ticket is None

    async def test_advancing_an_empty_queue_changes_nothing(
        self, repository: QueueRepository, clinic_id: str
    ) -> None:
        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.outcome is AdvanceOutcome.QUEUE_EMPTY
        assert (advance.now_serving, advance.completed) == (None, None)

    async def test_advancing_an_unknown_clinic_is_reported_as_such(
        self, repository: QueueRepository
    ) -> None:
        with pytest.raises(ClinicNotFoundError):
            await repository.advance_clinic_queue("no-such-clinic")

    async def test_the_queue_drains_one_patient_at_a_time(
        self,
        repository: QueueRepository,
        session: AsyncSession,
        clinic_id: str,
    ) -> None:
        # The whole point of the feature: before it existed, a queue
        # could only ever grow.
        users = []
        for index in range(4):
            user = await UserRepository(session).create_user(
                email=f"drain{index}@example.com",
                hashed_password="hashed",
                full_name=f"Drain {index}",
            )
            await session.flush()
            users.append(user.id)
        for user_id in users:
            await repository.join_queue(clinic_id=clinic_id, user_id=user_id)

        seen: list[int] = []
        for _ in range(4):
            advance = await repository.advance_clinic_queue(clinic_id)
            assert advance.now_serving is not None
            seen.append(advance.now_serving.ticket_number)

        # Called strictly in ticket order.
        assert seen == [1, 2, 3, 4]

        final = await repository.advance_clinic_queue(clinic_id)
        assert final.outcome is AdvanceOutcome.COMPLETED_LAST
        assert (await repository.get_clinics_with_queue_status())[0].waiting_count == 0

    async def test_a_cancelled_patient_is_skipped(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        first = await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        second = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )
        await repository.cancel_reservation(first.id)

        advance = await repository.advance_clinic_queue(clinic_id)

        assert advance.now_serving is not None
        assert advance.now_serving.id == second.id


class TestTheQueueStatusReflectsConsultations:
    async def test_the_patient_in_the_room_is_not_counted_as_waiting(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.join_queue(clinic_id=clinic_id, user_id=other_patient_id)
        await repository.advance_clinic_queue(clinic_id)

        queue = (await repository.get_clinics_with_queue_status())[0]

        # Two people present, but only one still to be called.
        assert queue.waiting_count == 1
        assert queue.now_serving_ticket == 1

    async def test_an_idle_room_reports_no_ticket(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)

        queue = (await repository.get_clinics_with_queue_status())[0]

        assert queue.now_serving_ticket is None

    async def test_a_patient_in_the_room_still_counts_as_ahead_of_you(
        self,
        repository: QueueRepository,
        clinic_id: str,
        patient_id: str,
        other_patient_id: str,
    ) -> None:
        # Excluding them would tell everyone behind that they had moved
        # up, when nothing had actually finished.
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        mine = await repository.join_queue(
            clinic_id=clinic_id, user_id=other_patient_id
        )
        await repository.advance_clinic_queue(clinic_id)

        refreshed = await repository.get_reservation_by_id(mine.id)

        assert refreshed is not None
        assert refreshed.people_ahead == 1

    async def test_being_called_in_is_still_an_active_place(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.advance_clinic_queue(clinic_id)

        mine = await repository.get_active_reservation_for_user(patient_id)

        assert mine is not None
        assert mine.is_in_consultation

    async def test_a_patient_in_the_room_cannot_take_a_second_ticket(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)
        await repository.advance_clinic_queue(clinic_id)

        with pytest.raises(AlreadyInQueueError):
            await repository.join_queue(clinic_id=clinic_id, user_id=patient_id)


class TestRecordsAreNotOrmObjects:
    async def test_callers_never_receive_a_sqlalchemy_object(
        self, repository: QueueRepository, clinic_id: str, patient_id: str
    ) -> None:
        # Layer 4's whole purpose: Layers 2 and 3 see plain data, so a
        # storage swap would touch only this module.
        reservation = await repository.join_queue(
            clinic_id=clinic_id, user_id=patient_id
        )
        queues = await repository.get_clinics_with_queue_status()

        for record in (reservation, queues[0]):
            assert not hasattr(record, "_sa_instance_state")
            with pytest.raises((AttributeError, TypeError)):
                record.id = "mutated"  # type: ignore[misc]
