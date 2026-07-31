"""Pydantic schemas for Inspection — نظام المعاينات المحمي."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.inspection import MIZAN_COMMISSION_RATE, InspectionStatus


class InspectionCreate(BaseModel):
    property_id: int
    buyer_id: int
    scheduled_at: datetime
    status: InspectionStatus = InspectionStatus.pending
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
    meeting_point: str | None = None
    confirmed_at: datetime | None = None


class InspectionBookRequest(BaseModel):
    """حجز معاينة — موافقة صريحة على عمولة الميزان 1.5% مطلوبة."""

    property_id: int
    buyer_id: int
    scheduled_at: datetime
    commission_agreed: Literal[True] = Field(
        ...,
        description="موافقة صريحة على تعهد عمولة الميزان 1.5% — يجب أن تكون True",
    )


class InspectionBookResponse(BaseModel):
    id: int
    property_id: int
    buyer_id: int
    scheduled_at: datetime
    status: InspectionStatus
    commission_agreed: bool
    commission_rate: float = MIZAN_COMMISSION_RATE
    inspection_code: str
    district: str
    meeting_point_hidden: bool = True
    message: str = (
        "تم حجز المعاينة بانتظار تأكيد المالك. "
        "نقطة التلاقي والتذكرة المتبادلة تُظهران بعد التأكيد فقط."
    )


class InspectionConfirmRequest(BaseModel):
    """تأكيد المعاينة من المالك — يكشف نقطة التلاقي والتذكرة."""

    inspection_code: str = Field(..., min_length=4, max_length=20)
    owner_id: int = Field(..., description="معرّف المالك للتحقق من الصلاحية")


class InspectionConfirmResponse(BaseModel):
    id: int
    property_id: int
    buyer_id: int
    scheduled_at: datetime
    status: InspectionStatus
    commission_agreed: bool
    commission_rate: float = MIZAN_COMMISSION_RATE
    inspection_code: str
    meeting_point: str
    confirmed_at: datetime
    mutual_ticket: dict
    message: str = "تم تأكيد الموعد. نقطة التلاقي والتذكرة المتبادلة جاهزتان."
