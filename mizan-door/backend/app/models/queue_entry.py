import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.clinic import Clinic
    from app.models.patient import Patient


class QueueStatus(str, enum.Enum):
    WAITING = "waiting"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    queue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QueueStatus] = mapped_column(
        SAEnum(QueueStatus, name="queue_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=QueueStatus.WAITING,
    )
    is_urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clinic: Mapped["Clinic"] = relationship(back_populates="queue_entries")
    patient: Mapped["Patient"] = relationship(back_populates="queue_entries")
