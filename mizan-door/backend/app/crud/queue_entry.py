import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.queue_entry import QueueEntry, QueueStatus
from app.schemas.queue_entry import QueueEntryCreate, QueueEntryUpdate


def _today_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


async def create_queue_entry(db: AsyncSession, data: QueueEntryCreate) -> QueueEntry:
    """Join the queue. Assigns the next sequential ticket number for the clinic, per day."""
    start, end = _today_bounds()
    result = await db.execute(
        select(func.max(QueueEntry.queue_number)).where(
            QueueEntry.clinic_id == data.clinic_id,
            QueueEntry.joined_at >= start,
            QueueEntry.joined_at < end,
        )
    )
    current_max = result.scalar()
    next_number = (current_max or 0) + 1

    entry = QueueEntry(
        clinic_id=data.clinic_id,
        patient_id=data.patient_id,
        queue_number=next_number,
        is_urgent=data.is_urgent,
        status=QueueStatus.WAITING,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_queue_entry(db: AsyncSession, entry_id: uuid.UUID) -> QueueEntry | None:
    result = await db.execute(
        select(QueueEntry)
        .options(selectinload(QueueEntry.patient))
        .where(QueueEntry.id == entry_id)
    )
    return result.scalar_one_or_none()


async def list_queue_entries_for_clinic(
    db: AsyncSession, clinic_id: uuid.UUID, today_only: bool = True
) -> list[QueueEntry]:
    query = select(QueueEntry).options(selectinload(QueueEntry.patient)).where(
        QueueEntry.clinic_id == clinic_id
    )
    if today_only:
        start, end = _today_bounds()
        query = query.where(QueueEntry.joined_at >= start, QueueEntry.joined_at < end)
    query = query.order_by(QueueEntry.is_urgent.desc(), QueueEntry.queue_number.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_queue_entry(db: AsyncSession, entry: QueueEntry, data: QueueEntryUpdate) -> QueueEntry:
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_queue_entry(db: AsyncSession, entry: QueueEntry) -> None:
    await db.delete(entry)
    await db.commit()
