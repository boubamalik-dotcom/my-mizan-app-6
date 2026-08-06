"""Pydantic request/response models for the Mizan Door API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.queue_entry import QueueStatus


# ---------------------------------------------------------------------------
# Clinic
# ---------------------------------------------------------------------------
class ClinicBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    specialty: str = Field(..., min_length=1, max_length=255)


class ClinicCreate(ClinicBase):
    """Used internally when registering a clinic together with its first staff account."""


class ClinicResponse(ClinicBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Auth (clinic staff)
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    email: EmailStr
    full_name: str
    created_at: datetime


class RegisterRequest(BaseModel):
    """Payload for POST /auth/register - creates a clinic and its first staff account together."""

    clinic_name: str = Field(..., min_length=1, max_length=255)
    specialty: str = Field(..., min_length=1, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    clinic: ClinicResponse


class MeResponse(BaseModel):
    user: UserResponse
    clinic: ClinicResponse


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
