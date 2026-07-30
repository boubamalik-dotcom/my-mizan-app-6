"""Pydantic schemas for Property — بما فيها Privacy Shield."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.property import DocumentType, OranDistrict, PropertyStatus


class PropertyCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    price: float = Field(..., gt=0)
    address: str = Field(..., min_length=3, max_length=255)
    district: OranDistrict
    document_type: DocumentType
    status: PropertyStatus = PropertyStatus.available
    owner_id: int


class PropertyRead(BaseModel):
    """Full property payload (owner / post-create)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    price: float
    address: str
    district: OranDistrict
    document_type: DocumentType
    status: PropertyStatus
    owner_id: int
    mizan_evaluation: dict[str, Any] | None = None


class PropertyPublicRead(BaseModel):
    """
    قائمة عامة مع Privacy Shield:
    - لا يظهر رقم هاتف المالك
    - لا يظهر العنوان الدقيق (الحي فقط)
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    price: float
    district: OranDistrict
    document_type: DocumentType
    status: PropertyStatus
    approximate_location: str
    address_hidden: bool = True
    owner_contact_hidden: bool = True
    mizan_evaluation: dict[str, Any] | None = None
    privacy_note: str = (
        "درع الخصوصية: العنوان الدقيق ورقم المالك يُكشفان بعد تأكيد المعاينة فقط."
    )


class PropertyCreateResponse(BaseModel):
    """استجابة إضافة عقار مع تقييم الميزان المحفوظ."""

    property: PropertyRead
    mizan_evaluation: dict[str, Any]
    message: str = "تم نشر العقار مع تقييم منطق الميزان."
