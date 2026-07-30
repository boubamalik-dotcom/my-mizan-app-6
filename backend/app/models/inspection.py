"""Inspection model — نظام المعاينات (منطق الميزان 1.5%)."""

from __future__ import annotations

import enum
import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# عمولة الميزان عند الموافقة على المعاينة
MIZAN_COMMISSION_RATE = 0.015  # 1.5%


class InspectionStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    completed = "completed"


def generate_inspection_code() -> str:
    """Generate a short unique inspection code (e.g. MZ-A1B2C3)."""
    return f"MZ-{secrets.token_hex(3).upper()}"


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspection_status", native_enum=False),
        default=InspectionStatus.pending,
        nullable=False,
    )
    # True = الموافقة على عمولة الميزان بنسبة 1.5%
    commission_agreed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    inspection_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        default=generate_inspection_code,
        index=True,
    )
    # تُملأ فقط بعد تأكيد المالك — نقطة التلاقي (العنوان الدقيق)
    meeting_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    listed_property: Mapped["Property"] = relationship(
        "Property",
        back_populates="inspections",
        foreign_keys=[property_id],
    )
    buyer: Mapped["User"] = relationship(
        "User",
        back_populates="inspections",
        foreign_keys=[buyer_id],
    )

    @property
    def commission_rate(self) -> float | None:
        """Return 1.5% when commission is agreed, otherwise None."""
        return MIZAN_COMMISSION_RATE if self.commission_agreed else None
