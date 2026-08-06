import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic import Clinic
from app.schemas.clinic import ClinicCreate, ClinicUpdate


async def create_clinic(db: AsyncSession, data: ClinicCreate) -> Clinic:
    clinic = Clinic(name=data.name, specialty=data.specialty)
    db.add(clinic)
    await db.commit()
    await db.refresh(clinic)
    return clinic


async def get_clinic(db: AsyncSession, clinic_id: uuid.UUID) -> Clinic | None:
    return await db.get(Clinic, clinic_id)


async def list_clinics(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[Clinic]:
    result = await db.execute(select(Clinic).offset(skip).limit(limit).order_by(Clinic.created_at))
    return list(result.scalars().all())


async def update_clinic(db: AsyncSession, clinic: Clinic, data: ClinicUpdate) -> Clinic:
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(clinic, field, value)
    await db.commit()
    await db.refresh(clinic)
    return clinic


async def delete_clinic(db: AsyncSession, clinic: Clinic) -> None:
    await db.delete(clinic)
    await db.commit()
