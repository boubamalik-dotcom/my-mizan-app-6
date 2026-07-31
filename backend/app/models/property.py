"""Property model — عقارات وهران."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OranDistrict(str, enum.Enum):
    bir_el_djir = "بئر الجير"
    el_akid_lotfi = "العقيد لطفي"
    usto = "USTO"
    corniche = "الكورنيش"


class DocumentType(str, enum.Enum):
    notarial_deed = "عقد توثيقي"
    land_register = "دفتر عقاري"
    customary = "عرفي"


class PropertyStatus(str, enum.Enum):
    available = "available"
    under_inspection = "under_inspection"
    reserved = "reserved"
    sold = "sold"


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[OranDistrict] = mapped_column(
        Enum(OranDistrict, name="oran_district", native_enum=False),
        nullable=False,
        index=True,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=False),
        nullable=False,
    )
    status: Mapped[PropertyStatus] = mapped_column(
        Enum(PropertyStatus, name="property_status", native_enum=False),
        default=PropertyStatus.available,
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # تقييم منطق الميزان عند النشر (عادل / مرتفع / منخفض + تعليل)
    mizan_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="owned_properties",
        foreign_keys=[owner_id],
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        "Inspection",
        back_populates="listed_property",
        foreign_keys="Inspection.property_id",
    )
