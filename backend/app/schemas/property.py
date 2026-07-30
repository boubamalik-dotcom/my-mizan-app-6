"""Pydantic schemas for Property."""

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
