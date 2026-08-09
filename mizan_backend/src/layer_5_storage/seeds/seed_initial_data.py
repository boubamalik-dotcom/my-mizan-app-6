"""Development seed: registers a handful of clinics so Mizan Door has
something to show.

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
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from ..db_config import async_session_factory
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


if __name__ == "__main__":
    count = asyncio.run(seed_clinics())
    logger.info("Seed complete: %d clinic(s) created.", count)
