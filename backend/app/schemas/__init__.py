"""Pydantic schemas for El Mizan Real Estate API."""

from app.schemas.ai import (
    EvaluatePriceRequest,
    EvaluatePriceResponse,
    ParsePromptRequest,
    ParsePromptResponse,
)
from app.schemas.inspection import InspectionCreate, InspectionRead
from app.schemas.property import PropertyCreate, PropertyRead
from app.schemas.user import UserCreate, UserRead

__all__ = [
    "UserCreate",
    "UserRead",
    "PropertyCreate",
    "PropertyRead",
    "InspectionCreate",
    "InspectionRead",
    "EvaluatePriceRequest",
    "EvaluatePriceResponse",
    "ParsePromptRequest",
    "ParsePromptResponse",
]
