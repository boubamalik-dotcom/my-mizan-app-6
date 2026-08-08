"""Layer 2 — Authentication controller.

`AuthController` orchestrates registration, login, and current-user
resolution:

1. Calls Layer 3 (`AuthService`) to hash/verify passwords and to
   issue/decode JWTs — pure logic, no I/O.
2. Uses Layer 4 (`UnitOfWork`, `UserRepository`) to read/write user
   accounts atomically.
3. Catches every domain exception raised by Layers 3/4
   (`auth_exceptions.py`) and translates it into the appropriate
   FastAPI `HTTPException`, so this is the *only* place in the backend
   where an authentication domain error becomes an HTTP status code.

`auth_routes.py` and `deps.py` stay thin adapters over this class:
neither contains business logic or exception-translation logic
itself.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, Tuple

from fastapi import HTTPException, status

from ...layer_3_business.auth.auth_exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
)
from ...layer_3_business.auth.auth_service import AuthService
from ...layer_4_data_access.repositories.user_repository import UserRecord
from ...layer_4_data_access.uow.transaction_manager import UnitOfWork


class AuthController:
    """Coordinates Layer 3 authentication logic and Layer 4
    transactional persistence to serve the authentication REST
    endpoints and the `get_current_user` dependency."""

    def __init__(
        self,
        *,
        auth_service: AuthService,
        unit_of_work_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> None:
        """
        Args:
            auth_service: The Layer 3 service used to hash/verify
                passwords and issue/decode JWTs.
            unit_of_work_factory: A zero-argument callable returning a
                fresh, not-yet-entered `UnitOfWork` each time it is
                invoked. Defaults to the `UnitOfWork` class itself (a
                class is a valid factory for its own instances).
                Injected so tests can point every unit of work this
                controller opens at an isolated test database.
        """
        self._auth_service = auth_service
        self._unit_of_work_factory = unit_of_work_factory

    async def register(
        self, *, email: str, password: str, full_name: str
    ) -> UserRecord:
        """Registers a new user account.

        Checks for an existing account with the same email via Layer 4
        *before* hashing the password or attempting to create the
        row — the common, race-free happy path — while
        `UserRepository.create_user` still enforces the same rule at
        the database's unique-constraint level as a backstop against
        the narrow window between that check and the write.

        Args:
            email: The new account's unique email address.
            password: The chosen password, in plaintext (hashed here,
                never persisted as-is).
            full_name: The user's display name.

        Returns:
            The newly created account's `UserRecord`.

        Raises:
            HTTPException: 400 if `email` is already registered.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                existing = await uow.users.get_user_by_email(email)
                if existing is not None:
                    raise UserAlreadyExistsError(email)

                hashed_password = self._auth_service.hash_password(password)
                user = await uow.users.create_user(
                    email=email, hashed_password=hashed_password, full_name=full_name
                )
                await uow.commit()

        return user

    async def login(self, *, email: str, password: str) -> Tuple[UserRecord, str]:
        """Authenticates a user and issues an access token.

        Args:
            email: The claimed account's email address.
            password: The password supplied at login time.

        Returns:
            A `(user, access_token)` tuple.

        Raises:
            HTTPException: 401 if the email/password combination does
                not match a registered, active account. The same
                status and message are returned whether the email is
                unregistered or the password is simply wrong, so a
                caller cannot enumerate valid accounts by observing the
                difference.
        """
        with self._translate_domain_errors():
            async with self._unit_of_work_factory() as uow:
                user = await uow.users.get_user_by_email(email)

            self._auth_service.authenticate(
                plain_password=password,
                hashed_password=user.hashed_password if user is not None else None,
            )
            # `authenticate` raises InvalidCredentialsError above
            # whenever `user` is None, so by this point it cannot be.
            assert user is not None

            if not user.is_active:
                raise InvalidCredentialsError()

            access_token = self._auth_service.create_access_token(subject=user.email)

        return user, access_token

    async def get_current_user(self, token: str) -> UserRecord:
        """Resolves the user identified by a bearer access token —
        the core of the `get_current_user` dependency used to protect
        routes.

        Args:
            token: The raw JWT access token (without the `"Bearer "`
                prefix), as issued by `login`.

        Returns:
            The token's associated `UserRecord`.

        Raises:
            HTTPException: 401 if the token is malformed, expired, has
                an invalid signature, or refers to an account that no
                longer exists or has been deactivated.
        """
        with self._translate_domain_errors():
            payload = self._auth_service.decode_access_token(token)

            async with self._unit_of_work_factory() as uow:
                user = await uow.users.get_user_by_email(payload.subject)

            if user is None or not user.is_active:
                raise InvalidTokenError(
                    "The user for this access token no longer exists or "
                    "has been deactivated."
                )

        return user

    # -- Internal helpers -------------------------------------------------

    @staticmethod
    @contextmanager
    def _translate_domain_errors() -> Iterator[None]:
        """Context manager translating every domain exception Layers
        3/4 can raise into the matching `HTTPException`, so each
        public method above needs only one `with` statement instead of
        repeating this mapping.

        Mapping:

        * `UserAlreadyExistsError` -> 400 Bad Request
        * `InvalidCredentialsError` -> 401 Unauthorized
        * `InvalidTokenError` -> 401 Unauthorized
        """
        try:
            yield
        except UserAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except InvalidCredentialsError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
