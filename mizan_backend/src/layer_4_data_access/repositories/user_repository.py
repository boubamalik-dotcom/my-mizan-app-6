"""Layer 4 — async repository abstracting SQLAlchemy-based user
account persistence.

Mirrors `wallet_repository.py`'s approach: a single concrete class
that is the only place besides Layer 5 itself that touches a
SQLAlchemy `AsyncSession` or the `UserModel` ORM class. Every method
returns a plain `UserRecord` dataclass, never an ORM object, so Layers
2/3 never see SQLAlchemy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...layer_3_business.auth.auth_exceptions import UserAlreadyExistsError
from ...layer_5_storage.models.user_model import UserModel


@dataclass(frozen=True, slots=True)
class UserRecord:
    """An immutable snapshot of a user account's persisted state,
    fully decoupled from the underlying `UserModel` — callers never
    need to import (or even know about) SQLAlchemy."""

    id: str
    email: str
    hashed_password: str
    full_name: str
    is_active: bool
    created_at: datetime


class UserRepository:
    """Async repository for user accounts.

    Bound to a single `AsyncSession` for its entire lifetime —
    typically one per `UnitOfWork` transaction (see
    `layer_4_data_access/uow/transaction_manager.py`) — so every
    read/write it performs participates in that one atomic
    transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: The `AsyncSession` this repository will use for
                every operation. Its transaction boundary (commit or
                rollback) is owned by the caller, not by this class.
        """
        self._session = session

    async def get_user_by_email(self, email: str) -> Optional[UserRecord]:
        """Fetches a user account by its email address.

        Args:
            email: The email address to look up.

        Returns:
            A `UserRecord` snapshot, or `None` if no user is
            registered under that email.
        """
        statement = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(statement)
        user = result.scalar_one_or_none()
        return self._to_record(user) if user is not None else None

    async def create_user(
        self, *, email: str, hashed_password: str, full_name: str
    ) -> UserRecord:
        """Creates and persists a new, active user account.

        `hashed_password` must already be a bcrypt hash produced by
        `AuthService.hash_password` — this method never hashes a
        plaintext password itself, keeping that responsibility
        entirely in Layer 3.

        Args:
            email: The new account's unique email address.
            hashed_password: The bcrypt hash of the user's chosen
                password.
            full_name: The user's display name.

        Returns:
            A `UserRecord` snapshot of the newly created account.

        Raises:
            UserAlreadyExistsError: If `email` is already registered.
                This is a defense-in-depth check at the database's
                unique-constraint level; callers should also check via
                `get_user_by_email` beforehand for a clearer, race-free
                happy path.
        """
        user = UserModel(email=email, hashed_password=hashed_password, full_name=full_name)
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise UserAlreadyExistsError(email) from exc
        return self._to_record(user)

    @staticmethod
    def _to_record(user: UserModel) -> UserRecord:
        """Maps a `UserModel` row to its plain-data `UserRecord`
        counterpart."""
        return UserRecord(
            id=user.id,
            email=user.email,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
        )
