"""Pydantic request/response models for the Mizan Door API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.queue_entry import QueueStatus


# ---------------------------------------------------------------------------
# Clinic
# ---------------------------------------------------------------------------
class ClinicBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    specialty: str = Field(..., min_length=1, max_length=255)


class ClinicCreate(ClinicBase):
    """Payload for POST /clinics."""


class ClinicResponse(ClinicBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------
class PatientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=1, max_length=32)


class PatientCreate(PatientBase):
    """Payload for POST /patients."""


class PatientResponse(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# QueueEntry
# ---------------------------------------------------------------------------
class QueueEntryCreate(BaseModel):
    """Payload for POST /clinics/{clinic_id}/queue. clinic_id comes from the path."""

    patient_id: uuid.UUID
    is_urgent: bool = False


class QueueEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    queue_number: int
    status: QueueStatus
    is_urgent: bool
    joined_at: datetime
    patient: PatientResponse
