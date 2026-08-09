"""Development seed: registers a handful of clinics and property
listings so Mizan Door and Oran Real Estate have something to show.

Run from the backend root, against whatever `DATABASE_URL` points at::

    python -m src.layer_5_storage.seeds.seed_initial_data

**Development and demo only.** Real clinics are onboarded
administratively, not by a script with names hardcoded in it. The
script is idempotent — it skips any clinic whose name is already
registered — so running it twice does not create duplicates, but it is
still not something to point at production.

Deliberately written against Layer 5 alone: the session factory from
`db_config` and `ClinicModel` itself, with no `UnitOfWork` and no
repository. Everything under `layer_5_storage/` is forbidden from
importing Layers 2, 3, or 4 (`tests/test_layer_isolation.py`), and a
seed script is no exception — it writes rows, which is exactly what
this layer is for.

The four clinics deliberately cover every state the queue screen can
render: a short queue, a long one, an empty one, and a clinic that has
stopped admitting patients. Without that spread, most of the UI is
unreachable in a demo, and unreachable UI is unreviewed UI.

The property listings follow the same principle for the amenity filter
bar: between them they cover every one of the four premium amenities,
and no single listing has all four, so selecting two chips genuinely
narrows the results instead of either matching everything or nothing.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from decimal import Decimal

from ..db_config import async_session_factory
from ..models.property_model import PropertyModel
from ..models.queue_model import ClinicModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#: `(name, specialty, district, service_rate_minutes, is_accepting)`.
SEED_CLINICS: tuple[tuple[str, str, str, int, bool], ...] = (
    ("عيادة الأمل للطب العام", "طب عام", "حي الصباح، وهران", 8, True),
    ("مركز النور لطب الأسنان", "طب الأسنان", "وسط المدينة، وهران", 15, True),
    ("عيادة الشفاء للأطفال", "طب الأطفال", "بئر الجير، وهران", 10, True),
    ("مركز الحياة للجلدية", "الأمراض الجلدية", "الصديقية، وهران", 12, False),
)


async def seed_clinics() -> int:
    """Registers any seed clinic that is not already present.

    Returns:
        How many clinics were created by this run.
    """
    async with async_session_factory() as session:
        existing = set(
            (await session.execute(select(ClinicModel.name))).scalars().all()
        )

        created = 0
        for name, specialty, district, rate, is_accepting in SEED_CLINICS:
            if name in existing:
                logger.info("Clinic already registered, skipping: %s", name)
                continue
            session.add(
                ClinicModel(
                    name=name,
                    specialty=specialty,
                    district=district,
                    service_rate_minutes=rate,
                    is_accepting_patients=is_accepting,
                )
            )
            created += 1
            logger.info("Registered clinic: %s", name)

        await session.commit()

    return created


#: `(title, district, price, bedrooms, bathrooms, area_sqm, featured,
#: pool, high_floor, king_bed, non_smoking)`.
SEED_PROPERTIES: tuple[
    tuple[str, str, str, int, int, int, bool, bool, bool, bool, bool], ...
] = (
    ("شقة فاخرة بإطلالة على البحر", "الصديقية، وهران", "42000000",
     4, 3, 210, True, True, True, True, False),
    ("بنتهاوس بانورامي في قلب المدينة", "وسط المدينة، وهران", "58500000",
     5, 4, 280, True, False, True, True, True),
    ("فيلا عصرية بمسبح خاص", "عين الترك، وهران", "76000000",
     6, 5, 420, False, True, False, False, True),
    ("شقة راقية قرب الواجهة البحرية", "المرسى الكبير، وهران", "31500000",
     3, 2, 155, False, False, False, True, True),
    ("دوبلكس واسع بحديقة خاصة", "بئر الجير، وهران", "49000000",
     5, 3, 260, False, False, False, True, False),
    ("استوديو حديث للمستثمرين", "حي الصباح، وهران", "12800000",
     1, 1, 62, False, False, True, False, True),
)


async def seed_properties() -> int:
    """Registers any seed listing not already present, matched by title.

    Returns:
        How many listings were created by this run.
    """
    async with async_session_factory() as session:
        existing = set(
            (await session.execute(select(PropertyModel.title))).scalars().all()
        )

        created = 0
        for (
            title, district, price, bedrooms, bathrooms, area,
            featured, pool, high_floor, king_bed, non_smoking,
        ) in SEED_PROPERTIES:
            if title in existing:
                logger.info("Listing already registered, skipping: %s", title)
                continue
            session.add(
                PropertyModel(
                    title=title,
                    description=f"{title} — {district}.",
                    price=Decimal(price),
                    district=district,
                    bedrooms=bedrooms,
                    bathrooms=bathrooms,
                    area_sqm=area,
                    is_featured=featured,
                    has_private_pool=pool,
                    is_high_floor=high_floor,
                    has_king_bed=king_bed,
                    is_non_smoking=non_smoking,
                )
            )
            created += 1
            logger.info("Registered listing: %s", title)

        await session.commit()

    return created


if __name__ == "__main__":
    clinics = asyncio.run(seed_clinics())
    listings = asyncio.run(seed_properties())
    logger.info(
        "Seed complete: %d clinic(s) and %d listing(s) created.",
        clinics,
        listings,
    )
