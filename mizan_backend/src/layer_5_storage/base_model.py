"""Layer 5 — shared SQLAlchemy declarative base and mixins.

This module (and everything else under `layer_5_storage/`) never
imports from Layers 2, 3, or 4: it only knows about ORM plumbing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the backend."""


def utcnow() -> datetime:
    """Timezone-aware "now", used as the default for timestamp
    columns so all persisted times are unambiguous UTC."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generates a string primary-key value. Kept as a plain function
    (rather than inline `default=lambda: str(uuid.uuid4())`) so it is
    easy to unit test and reuse across models."""
    return str(uuid.uuid4())


class TimestampMixin:
    """Adds `created_at`/`updated_at` columns to any model that mixes
    it in alongside `Base`."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
