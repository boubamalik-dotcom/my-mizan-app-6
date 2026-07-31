"""User model — El Mizan Real Estate."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    buyer = "buyer"
    seller = "seller"
    agent = "agent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owned_properties: Mapped[list["Property"]] = relationship(
        "Property",
        back_populates="owner",
        foreign_keys="Property.owner_id",
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        "Inspection",
        back_populates="buyer",
        foreign_keys="Inspection.buyer_id",
    )
