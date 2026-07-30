"""Pydantic schemas for El Mizan Real Estate API."""

from app.schemas.ai import (
    EvaluatePriceRequest,
    EvaluatePriceResponse,
    ParsePromptRequest,
    ParsePromptResponse,
)
from app.schemas.inspection import (
    InspectionBookRequest,
    InspectionBookResponse,
    InspectionConfirmRequest,
    InspectionConfirmResponse,
    InspectionCreate,
    InspectionRead,
)
from app.schemas.property import (
    PropertyCreate,
    PropertyCreateResponse,
    PropertyPublicRead,
    PropertyRead,
)
from app.schemas.user import UserCreate, UserRead

__all__ = [
    "UserCreate",
    "UserRead",
    "PropertyCreate",
    "PropertyCreateResponse",
    "PropertyPublicRead",
    "PropertyRead",
    "InspectionCreate",
    "InspectionRead",
    "InspectionBookRequest",
    "InspectionBookResponse",
    "InspectionConfirmRequest",
    "InspectionConfirmResponse",
    "EvaluatePriceRequest",
    "EvaluatePriceResponse",
    "ParsePromptRequest",
    "ParsePromptResponse",
]
