import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.queue_entry import QueueEntry
    from app.models.user import User


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    queue_entries: Mapped[list["QueueEntry"]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(back_populates="clinic", cascade="all, delete-orphan")
