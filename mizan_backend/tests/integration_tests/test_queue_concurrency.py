"""Integration tests proving Mizan Door's ticket numbering is safe under
**genuine** concurrency — many independent database connections, via a
real local PostgreSQL server, racing to join the same clinic.

This is the test the whole design of `QueueRepository.join_queue` exists
to pass. Handing out a ticket is a read-then-insert, so without the
``SELECT ... FOR UPDATE`` lock on the clinic row, two patients joining
in the same millisecond both read ``MAX(position) = 7`` and both try to
insert ``8``.

SQLite cannot exercise any of this: it funnels every ``:memory:``
connection through a single connection, serialises writers regardless,
and ignores ``FOR UPDATE`` outright. These tests are skipped
automatically when no local Postgres server is reachable at
`QUEUE_TEST_DATABASE_URL`.

`TestTheRaceIsReal` deliberately reproduces the unsafe version to show
the race is not hypothetical and that the safeguards actually fire — a
concurrency test that would pass against broken code proves nothing.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_3_business.queue.exceptions import AlreadyInQueueError
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.queue_model import ReservationModel

QUEUE_TEST_DATABASE_URL = os.environ.get(
    "QUEUE_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/mizan_queue_test",
)
# asyncpg (not SQLAlchemy's URL scheme) for the plain connectivity probe.
_ASYNCPG_URL = QUEUE_TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

#: Enough simultaneous joins that an unlocked implementation fails
#: essentially every run, while the suite still finishes quickly.
CONCURRENT_PATIENTS = 25


async def _postgres_available() -> bool:
    try:
        connection = await asyncio.wait_for(asyncpg.connect(_ASYNCPG_URL), timeout=1.0)
        await connection.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not asyncio.run(_postgres_available()),
    reason="No local Postgres server reachable for queue concurrency test.",
)
pytestmark = requires_postgres


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine(QUEUE_TEST_DATABASE_URL)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


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


async def _create_patients(
    session_factory: async_sessionmaker, count: int
) -> list[str]:
    """One registered account per racer: `queue_reservations.user_id` is
    a real foreign key, and the one-place-per-clinic rule means the
    racers have to be different people for the race to be about ticket
    numbering rather than about that rule."""
    async with UnitOfWork(session_factory) as uow:
        patients = [
            await uow.users.create_user(
                email=f"patient{index}@example.com",
                hashed_password="hashed",
                full_name=f"Patient {index}",
            )
            for index in range(count)
        ]
        await uow.commit()
    return [patient.id for patient in patients]


@pytest_asyncio.fixture
async def patient_ids(session_factory: async_sessionmaker) -> list[str]:
    return await _create_patients(session_factory, CONCURRENT_PATIENTS)


async def _join(
    session_factory: async_sessionmaker, clinic_id: str, user_id: str
) -> int:
    """Joins through the real Layer 4 path, in its own `UnitOfWork` —
    and therefore its own session, transaction, and connection, exactly
    as two simultaneous HTTP requests would."""
    async with UnitOfWork(session_factory) as uow:
        reservation = await uow.queues.join_queue(
            clinic_id=clinic_id, user_id=user_id
        )
        await uow.commit()
    return reservation.ticket_number


class TestSimultaneousJoinsGetSequentialTickets:
    async def test_no_two_patients_receive_the_same_ticket(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        # The requirement, stated directly: joining at the exact same
        # moment must never produce a duplicate.
        tickets = await asyncio.gather(
            *(
                _join(session_factory, clinic_id, patient_id)
                for patient_id in patient_ids
            )
        )

        assert len(set(tickets)) == len(tickets), f"duplicate tickets: {tickets}"

    async def test_the_tickets_are_exactly_one_through_n(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        # Stronger than "no duplicates": no gaps either, so the counter
        # neither repeated nor skipped under contention.
        tickets = await asyncio.gather(
            *(
                _join(session_factory, clinic_id, patient_id)
                for patient_id in patient_ids
            )
        )

        assert sorted(tickets) == list(range(1, CONCURRENT_PATIENTS + 1))

    async def test_every_racer_ends_up_persisted_exactly_once(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        await asyncio.gather(
            *(
                _join(session_factory, clinic_id, patient_id)
                for patient_id in patient_ids
            )
        )

        async with session_factory() as session:
            stored = await session.scalar(
                select(func.count(ReservationModel.id)).where(
                    ReservationModel.clinic_id == clinic_id
                )
            )
            distinct_positions = await session.scalar(
                select(func.count(func.distinct(ReservationModel.position))).where(
                    ReservationModel.clinic_id == clinic_id
                )
            )

        assert stored == CONCURRENT_PATIENTS
        assert distinct_positions == CONCURRENT_PATIENTS

    async def test_one_patient_tapping_twice_gets_exactly_one_place(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        # The duplicate-place check runs inside the same lock, so two
        # simultaneous taps cannot both find "no existing place".
        patient_id = patient_ids[0]

        results = await asyncio.gather(
            *(_join(session_factory, clinic_id, patient_id) for _ in range(5)),
            return_exceptions=True,
        )

        succeeded = [r for r in results if isinstance(r, int)]
        refused = [r for r in results if isinstance(r, AlreadyInQueueError)]

        assert len(succeeded) == 1
        assert len(refused) == 4


class TestDifferentClinicsDoNotBlockEachOther:
    async def test_joins_at_separate_clinics_run_independently(
        self, session_factory: async_sessionmaker, patient_ids: list[str]
    ) -> None:
        # The lock is on the clinic row, not the table: contention for
        # one queue must not serialise the whole feature.
        async with UnitOfWork(session_factory) as uow:
            clinics = [
                await uow.queues.create_clinic(
                    name=f"عيادة {index}",
                    specialty="طب عام",
                    district="وهران",
                    service_rate_minutes=5,
                )
                for index in range(5)
            ]
            await uow.commit()

        tickets = await asyncio.gather(
            *(
                _join(session_factory, clinics[index % 5].id, patient_id)
                for index, patient_id in enumerate(patient_ids)
            )
        )

        # Five clinics, five patients each, each numbered from one.
        assert sorted(tickets) == sorted([1, 2, 3, 4, 5] * 5)


class TestTheRaceIsReal:
    """Reproduces the unsafe implementation, to show these tests would
    actually catch a regression rather than passing vacuously."""

    @staticmethod
    async def _join_without_the_lock(
        session_factory: async_sessionmaker, clinic_id: str, user_id: str
    ) -> int:
        """`join_queue` with the ``FOR UPDATE`` lock removed: read the
        highest ticket, add one, insert. This is the obvious
        implementation, and it is wrong."""
        async with session_factory() as session:
            highest = await session.scalar(
                select(func.max(ReservationModel.position)).where(
                    ReservationModel.clinic_id == clinic_id
                )
            )
            position = (highest or 0) + 1
            # Give every racer time to read the same maximum before any
            # of them writes, so the race is reproduced deterministically
            # rather than depending on scheduling luck.
            await asyncio.sleep(0.05)
            session.add(
                ReservationModel(
                    clinic_id=clinic_id, user_id=user_id, position=position
                )
            )
            await session.commit()
            return position

    async def test_without_the_lock_patients_collide_on_the_same_ticket(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        racers = 5
        results = await asyncio.gather(
            *(
                self._join_without_the_lock(session_factory, clinic_id, patient_id)
                for patient_id in patient_ids[:racers]
            ),
            return_exceptions=True,
        )

        persisted = [r for r in results if isinstance(r, int)]
        rejected = [r for r in results if isinstance(r, IntegrityError)]

        # How many racers happen to read before the first commit varies
        # with connection scheduling, so the exact split is not fixed.
        # What is fixed is that some of them computed a ticket another
        # had already taken — the race is real, not theoretical.
        assert rejected, f"expected a collision, got {results}"
        assert len(persisted) < racers, (
            "every racer succeeded, so this run did not actually race; "
            f"got {results}"
        )
        # And the collision was stopped by the constraint rather than
        # persisted: no two patients ended up holding one ticket.
        assert len(set(persisted)) == len(persisted)

    async def test_the_locked_implementation_survives_the_same_race(
        self,
        session_factory: async_sessionmaker,
        clinic_id: str,
        patient_ids: list[str],
    ) -> None:
        # Same shape as the test above, through the real code path:
        # every racer succeeds, and each gets its own ticket.
        tickets = await asyncio.gather(
            *(
                _join(session_factory, clinic_id, patient_id)
                for patient_id in patient_ids[:5]
            )
        )

        assert sorted(tickets) == [1, 2, 3, 4, 5]
