"""Pydantic schemas for Inspection — نظام المعاينات."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.inspection import InspectionStatus


class InspectionCreate(BaseModel):
    property_id: int
    buyer_id: int
    scheduled_at: datetime
    status: InspectionStatus = InspectionStatus.pending
    # True = الموافقة على عمولة الميزان 1.5%
    commission_agreed: bool = False
    inspection_code: str | None = Field(
        default=None,
        description="Optional custom code; auto-generated if omitted",
        max_length=20,
    )


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    buyer_id: int
    scheduled_at: datetime
    status: InspectionStatus
    commission_agreed: bool
    inspection_code: str
    commission_rate: float | None = Field(
        default=None,
        description="1.5% when commission_agreed is True, otherwise null",
    )
