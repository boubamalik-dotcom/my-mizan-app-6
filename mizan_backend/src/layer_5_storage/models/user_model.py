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

#: The role assigned to a newly created account when none is given.
#:
#: Stored as a plain string rather than a database enum, and kept in
#: sync with `layer_3_business.authz.roles.Role` by a test rather than
#: by an import: Layer 5 never imports from Layer 3, and a native enum
#: type would make adding a role a schema migration instead of a policy
#: change. Validation of the value belongs to Layer 3 (`Role.parse`),
#: which is where an unrecognised role becomes a loud error.
DEFAULT_USER_ROLE = "user"


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
    #: The account's access-control role — see
    #: `layer_3_business.authz.roles.Role` for what each one grants.
    #: Indexed because "list every auditor" is a question compliance
    #: reviews ask routinely.
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DEFAULT_USER_ROLE, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract. Deliberately omits `hashed_password`."""
        return (
            f"UserModel(id={self.id!r}, email={self.email!r}, "
            f"role={self.role!r}, is_active={self.is_active!r})"
        )
