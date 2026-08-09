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
from typing import Callable, Iterable, Iterator, Optional, Tuple

from fastapi import HTTPException, status

from ...layer_3_business.authz.authorization_service import AuthorizationService
from ...layer_3_business.auth.auth_exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
)
from ...layer_3_business.auth.auth_service import AuthService, TokenPayload
from ...layer_4_data_access.cache.token_blocklist import TokenBlocklist
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
        authorization_service: Optional[AuthorizationService] = None,
        bootstrap_admin_emails: Iterable[str] = (),
        token_blocklist: Optional[TokenBlocklist] = None,
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
            authorization_service: The Layer 3 service deciding a new
                account's initial role.
            bootstrap_admin_emails: Addresses granted `admin` on
                registration, from `config.Settings`. See
                `AuthorizationService.initial_role_for` for why this
                exists at all.
            token_blocklist: Where revoked tokens are recorded. `None`
                disables revocation entirely — every syntactically valid
                token stays usable until it expires, and `logout`
                becomes a no-op. Only appropriate for a deployment that
                has consciously accepted that; the composition root
                always supplies one.
        """
        self._auth_service = auth_service
        self._unit_of_work_factory = unit_of_work_factory
        self._authorization_service = authorization_service or AuthorizationService()
        self._bootstrap_admin_emails = tuple(bootstrap_admin_emails)
        self._token_blocklist = token_blocklist

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
                role = self._authorization_service.initial_role_for(
                    email=email,
                    bootstrap_admin_emails=self._bootstrap_admin_emails,
                )
                user = await uow.users.create_user(
                    email=email,
                    hashed_password=hashed_password,
                    full_name=full_name,
                    role=role.value,
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

            if await self._is_revoked(payload):
                raise InvalidTokenError(
                    "This access token has been revoked. Please sign in again."
                )

            async with self._unit_of_work_factory() as uow:
                user = await uow.users.get_user_by_email(payload.subject)

            if user is None or not user.is_active:
                raise InvalidTokenError(
                    "The user for this access token no longer exists or "
                    "has been deactivated."
                )

        return user

    async def resolve_user_or_none(self, token: str) -> Optional[UserRecord]:
        """Resolves a bearer token to its user, or `None` if it does not
        resolve to an active account.

        The non-raising twin of [get_current_user], for callers that
        cannot use an `HTTPException`. The WebSocket handshake is the
        case: a connection that was never accepted has no HTTP response
        to carry a status code, so it must be closed with a WebSocket
        close code instead.

        Also closes a hole in the socket handshake: it previously
        validated only the token's signature and expiry, never loading
        the account, so an unexpired token belonging to a **deleted or
        deactivated** user still opened a connection. Going through the
        same lookup as the REST path means deactivation takes effect on
        the next connection attempt.
        """
        try:
            payload = self._auth_service.decode_access_token(token)
        except InvalidTokenError:
            return None

        # Checked here too, not just on the REST path: a revoked token
        # that could still open a WebSocket would be revoked in name
        # only, since the socket outlives the request that opened it.
        if await self._is_revoked(payload):
            return None

        async with self._unit_of_work_factory() as uow:
            user = await uow.users.get_user_by_email(payload.subject)

        if user is None or not user.is_active:
            return None
        return user

    async def logout(self, token: str) -> None:
        """Revokes `token`, so it stops working before it expires.

        Signing out has to mean something server-side. A JWT is valid
        because it verifies, not because a server remembers it, so
        "logging out" by deleting the client's copy leaves a fully
        working credential in every log, proxy cache, and browser
        history it ever passed through — usable until its `exp`.

        The blocklist entry lives exactly as long as the token has left
        (Layer 3's `seconds_until_expiry`), so the store stays bounded
        by active sessions rather than growing with every logout.

        Idempotent: revoking an already-revoked, already-expired, or
        unrecognised-but-well-formed token succeeds quietly. A client
        that cannot reliably log out will retry, and a second attempt
        must not fail.

        Raises:
            HTTPException: 401 if the token is malformed, expired, or
                has an invalid signature — there is nothing to revoke.
        """
        with self._translate_domain_errors():
            payload = self._auth_service.decode_access_token(token)

        if self._token_blocklist is None:
            return

        if payload.token_id is None:
            # Issued before tokens carried a `jti`. It cannot be revoked
            # individually, and blocking by any other property would
            # mean blocking every token that shares it. Such a token
            # expires on its own within the access-token lifetime.
            return

        ttl_seconds = payload.seconds_until_expiry()
        if ttl_seconds <= 0:
            return

        await self._token_blocklist.revoke(
            payload.token_id, ttl_seconds=ttl_seconds
        )

    # -- Internal helpers -------------------------------------------------

    async def _is_revoked(self, payload: TokenPayload) -> bool:
        """Whether this specific token has been revoked.

        A token with no `jti` was issued before revocation existed and
        cannot appear in the blocklist, so it is treated as not
        revoked — the honest reading, and it still expires on its own.
        """
        if self._token_blocklist is None or payload.token_id is None:
            return False
        return await self._token_blocklist.is_revoked(payload.token_id)

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
