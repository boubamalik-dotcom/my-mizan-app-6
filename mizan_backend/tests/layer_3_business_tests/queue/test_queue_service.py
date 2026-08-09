"""Unit tests for Layer 3's pure clinic-queue rules.

No database, no event loop, no HTTP client — if any of these tests ever
needs one, a rule has leaked out of Layer 3.
"""
from __future__ import annotations

import pytest

from src.layer_3_business.queue.exceptions import (
    AlreadyInQueueError,
    ClinicNotAcceptingPatientsError,
    QueueDomainError,
    ReservationNotActiveError,
)
from src.layer_3_business.queue.queue_service import QueueService


@pytest.fixture
def service() -> QueueService:
    return QueueService()


class TestNextTicketNumber:
    def test_the_first_patient_of_the_day_gets_ticket_one(
        self, service: QueueService
    ) -> None:
        # One rather than zero: it is read aloud in a waiting room.
        assert service.next_ticket_number(None) == 1

    def test_each_ticket_follows_the_highest_already_issued(
        self, service: QueueService
    ) -> None:
        assert service.next_ticket_number(7) == 8

    def test_cancelled_tickets_are_not_reused(self, service: QueueService) -> None:
        # The caller passes the highest ticket *ever* issued, including
        # cancelled ones, so a gap left by someone leaving is never
        # filled. Two patients holding "ticket 8" over one day would
        # make the clinic's own record ambiguous.
        highest_ever_issued = 8
        assert service.next_ticket_number(highest_ever_issued) == 9

    def test_ticket_numbers_are_strictly_increasing(
        self, service: QueueService
    ) -> None:
        issued: list[int] = []
        highest = None
        for _ in range(50):
            highest = service.next_ticket_number(highest)
            issued.append(highest)

        assert issued == sorted(issued)
        assert len(set(issued)) == len(issued)


class TestEstimateWaitMinutes:
    def test_multiplies_queue_length_by_the_clinics_own_pace(
        self, service: QueueService
    ) -> None:
        assert (
            service.estimate_wait_minutes(people_ahead=3, service_rate_minutes=8) == 24
        )

    def test_two_clinics_with_the_same_queue_can_differ(
        self, service: QueueService
    ) -> None:
        # Which is the reason the rate lives on the clinic at all.
        dentist = service.estimate_wait_minutes(
            people_ahead=4, service_rate_minutes=15
        )
        general = service.estimate_wait_minutes(people_ahead=4, service_rate_minutes=8)
        assert (dentist, general) == (60, 32)

    def test_nobody_ahead_means_no_wait(self, service: QueueService) -> None:
        assert (
            service.estimate_wait_minutes(people_ahead=0, service_rate_minutes=10) == 0
        )

    @pytest.mark.parametrize(
        ("people_ahead", "service_rate_minutes"),
        [(-1, 10), (3, 0), (3, -5), (-2, -2)],
    )
    def test_never_returns_a_negative_wait(
        self, service: QueueService, people_ahead: int, service_rate_minutes: int
    ) -> None:
        # A negative estimate would render as a time in the past.
        assert (
            service.estimate_wait_minutes(
                people_ahead=people_ahead, service_rate_minutes=service_rate_minutes
            )
            == 0
        )


class TestClinicAdmissionRule:
    def test_an_open_clinic_passes(self, service: QueueService) -> None:
        service.ensure_clinic_accepts_patients(
            clinic_id="c1", is_accepting_patients=True
        )

    def test_a_closed_clinic_is_refused(self, service: QueueService) -> None:
        with pytest.raises(ClinicNotAcceptingPatientsError) as exc_info:
            service.ensure_clinic_accepts_patients(
                clinic_id="c1", is_accepting_patients=False
            )

        assert exc_info.value.clinic_id == "c1"

    def test_the_refusal_names_the_clinic(self, service: QueueService) -> None:
        # So the message is actionable rather than a bare "denied".
        with pytest.raises(ClinicNotAcceptingPatientsError, match="c1"):
            service.ensure_clinic_accepts_patients(
                clinic_id="c1", is_accepting_patients=False
            )


class TestOnePlacePerPatientRule:
    def test_a_patient_without_a_place_may_join(self, service: QueueService) -> None:
        service.ensure_not_already_queued(
            clinic_id="c1", user_id="u1", holds_active_place=False
        )

    def test_a_patient_already_queued_may_not_join_again(
        self, service: QueueService
    ) -> None:
        # One person holding two tickets would make the queue overstate
        # how many people are really waiting.
        with pytest.raises(AlreadyInQueueError) as exc_info:
            service.ensure_not_already_queued(
                clinic_id="c1", user_id="u1", holds_active_place=True
            )

        assert (exc_info.value.clinic_id, exc_info.value.user_id) == ("c1", "u1")


class TestReservationActivityRule:
    ACTIVE = ("waiting",)

    def test_a_waiting_reservation_is_active(self, service: QueueService) -> None:
        service.ensure_reservation_is_active(
            reservation_id="r1", status="waiting", active_statuses=self.ACTIVE
        )

    @pytest.mark.parametrize("status", ["served", "cancelled"])
    def test_a_terminal_reservation_is_not(
        self, service: QueueService, status: str
    ) -> None:
        with pytest.raises(ReservationNotActiveError) as exc_info:
            service.ensure_reservation_is_active(
                reservation_id="r1", status=status, active_statuses=self.ACTIVE
            )

        assert exc_info.value.status == status

    def test_cancelling_twice_is_refused_rather_than_ignored(
        self, service: QueueService
    ) -> None:
        # Silently succeeding would confirm a belief about the queue
        # that is already wrong.
        with pytest.raises(ReservationNotActiveError):
            service.ensure_reservation_is_active(
                reservation_id="r1", status="cancelled", active_statuses=self.ACTIVE
            )


class TestExceptionHierarchy:
    def test_every_queue_error_shares_one_base(self) -> None:
        # So Layer 2 can catch the whole family when it wants to, and
        # each member individually when it needs a specific status code.
        for error_type in (
            ClinicNotAcceptingPatientsError,
            AlreadyInQueueError,
            ReservationNotActiveError,
        ):
            assert issubclass(error_type, QueueDomainError)


class TestLayer3Purity:
    def test_the_rules_module_imports_no_framework(self) -> None:
        # `tests/test_layer_isolation.py` enforces this across the whole
        # layer; asserted here too so a violation names the queue rules
        # specifically rather than appearing as a generic layer failure.
        import inspect

        from src.layer_3_business.queue import queue_service

        source = inspect.getsource(queue_service)
        for forbidden in ("fastapi", "sqlalchemy", "pydantic", "redis"):
            assert forbidden not in source
