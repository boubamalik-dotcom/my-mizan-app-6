"""Layer 2 — Pydantic request/response schemas for Mizan Door's clinic
queue endpoints.

Field names here are the wire contract `mizan_frontend`'s Mizan Door
mini-program already parses (`lib/mini_programs/mizan_door/data/models/
queue_model.dart` and `reservation_model.dart`), so they are chosen to
match that client rather than to mirror the column names underneath.
Two places where the two deliberately differ:

* ``average_service_minutes`` is stored as ``clinics.service_rate_minutes``.
* ``position`` is **how many people are ahead**, derived at read time.
  The stored ``queue_reservations.position`` column is the immutable
  ticket number, exposed separately as ``ticket_number``.

Both are documented on the fields below, because a name meaning one
thing in the database and another on the wire is exactly the sort of
detail that gets misread later.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """FastAPI's standard error envelope, declared so the queue
    endpoints document their failures in the OpenAPI schema."""

    detail: str


class ClinicResponse(BaseModel):
    """A clinic's identity, as shown on a queue card."""

    id: str
    name: str
    specialty: str
    district: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "8f14e45f-ceea-467a-9c1f-1b3d8e2a9c77",
                "name": "عيادة الأمل للطب العام",
                "specialty": "طب عام",
                "district": "حي الصباح، وهران",
            }
        }
    }


class ClinicQueueResponse(BaseModel):
    """One clinic's queue as it stands right now."""

    clinic: ClinicResponse
    waiting_count: int = Field(
        description="Active tickets held right now — the number of people "
        "who would be ahead of someone joining at this moment."
    )
    average_service_minutes: int = Field(
        description="Minutes this clinic currently takes per patient "
        "(stored as `clinics.service_rate_minutes`). Sent so the client "
        "can render an estimate that matches the queue length beside it."
    )
    is_accepting_patients: bool = Field(
        description="False when the clinic has stopped admitting people. "
        "The queue is still returned so a patient can see why they cannot "
        "join, rather than the clinic silently disappearing from the list."
    )
    estimated_wait_minutes: int = Field(
        description="What someone joining now would likely wait: "
        "`waiting_count * average_service_minutes`, computed server-side "
        "so every client shows the same figure."
    )


class ReservationResponse(BaseModel):
    """The caller's own place in a clinic's queue."""

    id: str
    clinic_id: str
    clinic_name: str
    position: int = Field(
        description="How many people are ahead. **0 means next to be "
        "seen.** Derived at read time by counting active tickets below "
        "this one, so it shrinks as the queue moves — it is not the "
        "stored ticket number (see `ticket_number`)."
    )
    ticket_number: int = Field(
        description="The immutable per-clinic ticket issued at join "
        "time (`queue_reservations.position`). Never reused, never "
        "rewritten — this is the number called out in the waiting room."
    )
    estimated_wait_minutes: int
    status: str = Field(description="One of `waiting`, `served`, `cancelled`.")
    joined_at: datetime = Field(
        description="When the place was taken (`created_at`)."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "3b1f0c62-77a1-4c0e-8f2a-2b6b1d4e0a91",
                "clinic_id": "8f14e45f-ceea-467a-9c1f-1b3d8e2a9c77",
                "clinic_name": "عيادة الأمل للطب العام",
                "position": 2,
                "ticket_number": 9,
                "estimated_wait_minutes": 16,
                "status": "waiting",
                "joined_at": "2026-08-09T09:00:00Z",
            }
        }
    }


class QueueListResponse(BaseModel):
    """The `GET /queues` payload: every clinic's queue, plus the
    caller's own place if they hold one and identified themselves.

    An envelope rather than a bare list so one request answers both
    "what are the queues" and "where am I" — the two questions the
    queue screen opens with, which would otherwise be two round trips
    on a connection that may well be a phone on mobile data.
    """

    queues: list[ClinicQueueResponse]
    reservation: ReservationResponse | None = Field(
        default=None,
        description="The caller's active place, or null. Always null "
        "for an unauthenticated request, which cannot be attributed to "
        "anyone.",
    )
