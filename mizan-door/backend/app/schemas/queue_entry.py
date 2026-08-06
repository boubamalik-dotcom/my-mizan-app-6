import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue_entry import QueueStatus


class QueueEntryCreate(BaseModel):
    """Payload used by a patient to join a clinic's queue."""

    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    is_urgent: bool = False


class QueueEntryUpdate(BaseModel):
    status: QueueStatus | None = None
    is_urgent: bool | None = None


class QueueEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    queue_number: int
    status: QueueStatus
    is_urgent: bool
    joined_at: datetime


class QueueEntryWithPatient(QueueEntryRead):
    """Queue entry enriched with patient details, used for the clinic dashboard list."""

    patient_name: str = Field(..., description="Denormalized patient name for display")
    patient_phone: str = Field(..., description="Denormalized patient phone for display")
