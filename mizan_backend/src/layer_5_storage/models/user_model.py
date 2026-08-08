"""Layer 5 — SQLAlchemy ORM model for registered user accounts.

STRICT RULE: this module contains an ORM model only — no business
rules, no FastAPI/Pydantic imports, and no imports from Layers 2-4.
Password hashing happens in Layer 3 (`auth_service.py`); this model
only ever stores the resulting hash, never a plaintext password.
"""
from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base_model import Base, TimestampMixin, generate_uuid


class UserModel(Base, TimestampMixin):
    """A single registered user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    #: A bcrypt hash produced by
    #: `layer_3_business.auth.auth_service.AuthService.hash_password` —
    #: never a plaintext password.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract. Deliberately omits `hashed_password`."""
        return (
            f"UserModel(id={self.id!r}, email={self.email!r}, "
            f"is_active={self.is_active!r})"
        )
