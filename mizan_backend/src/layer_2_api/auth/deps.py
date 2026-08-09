"""Layer 2 — authentication dependencies for protecting routes.

This is the seam every other feature's routes (Wallet, Chat, and any
future mini-program endpoint) will `Depends()` on to require an
authenticated caller — exposing that seam is the whole reason this
module exists.
"""
from __future__ import annotations

from typing import Callable, Coroutine, Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...layer_3_business.authz.authorization_service import AuthorizationService
from ...layer_3_business.authz.authz_exceptions import (
    InvalidRoleError,
    PermissionDeniedError,
)
from ...layer_3_business.authz.roles import Permission, Role
from ...layer_4_data_access.cache.rate_limiter import RateLimiter
from ...layer_4_data_access.repositories.user_repository import UserRecord
from .auth_controller import AuthController

#: FastAPI's `HTTPBearer` security scheme both extracts the
#: `Authorization: Bearer <token>` header for us and registers the
#: requirement in the generated OpenAPI schema (Swagger UI shows a
#: padlock icon and an "Authorize" button for any route depending on
#: `get_current_user`). `auto_error=True` makes it raise its own 401
#: automatically when the header is missing entirely, before
#: `get_current_user` below is even called.
_bearer_scheme = HTTPBearer(
    auto_error=True,
    description="JWT access token issued by POST /auth/login.",
)


def get_auth_controller(request: Request) -> AuthController:
    """Resolves the app-wide `AuthController` singleton.

    Constructed once at startup in `main.py` (the composition root)
    and stored on `app.state`, so it is never re-instantiated per
    request.
    """
    return request.app.state.auth_controller


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    controller: AuthController = Depends(get_auth_controller),
) -> UserRecord:
    """FastAPI dependency resolving the authenticated caller from
    their bearer token.

    Use as ``current_user: UserRecord = Depends(get_current_user)`` on
    any route that should require authentication — this is the
    dependency the Wallet and Chat routes will adopt to become
    protected.

    Raises:
        HTTPException: 401 (via `HTTPBearer` itself) if the
            `Authorization` header is missing or not a bearer token;
            401 (via `AuthController.get_current_user`) if the token
            is malformed, expired, has an invalid signature, or refers
            to a user that no longer exists or is inactive.
    """
    return await controller.get_current_user(credentials.credentials)


#: Layer 3's authorization rules. Stateless and free of I/O, so unlike
#: `AuthController` there is nothing to construct per request or wire
#: through `app.state` — a module-level instance is the whole object.
_authorization_service = AuthorizationService()


def resolve_role(user: UserRecord) -> Role:
    """Resolves a persisted role string to Layer 3's `Role`.

    Raises:
        HTTPException: 500 if the stored value names no known role.
            That is a data-integrity fault in our own database, not a
            problem with the caller's request, and it must fail closed
            and loudly rather than be treated as "no role".
    """
    try:
        return Role.parse(user.role)
    except InvalidRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The account's role is not recognised by this server.",
        ) from exc


async def get_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """The raw bearer token, for the one route that needs the credential
    itself rather than the user behind it.

    `POST /auth/logout` revokes a specific token, so it needs the string
    that was presented — `get_current_user` deliberately discards it.
    """
    return credentials.credentials


def rate_limited(
    *,
    scope: str,
    attempts: int,
    window_seconds: int,
) -> Callable[..., Coroutine[None, None, None]]:
    """Builds a dependency that throttles a route by client IP.

    Applied to the unauthenticated endpoints, which are the ones an
    attacker can hammer without first obtaining anything: `login` is a
    password oracle, and `register` is free account creation.

    Keyed on `scope` as well as the address, so exhausting the login
    limit does not also lock the caller out of registering.

    Answers **429** with `Retry-After`, and adds `X-RateLimit-*` headers
    so a well-behaved client can back off before being refused.
    """

    async def dependency(request: Request, response: Response) -> None:
        limiter: Optional[RateLimiter] = getattr(
            request.app.state, "rate_limiter", None
        )
        if limiter is None:
            # No limiter configured: the composition root always supplies
            # one, so this is a bare test app rather than a production
            # path. Throttling nothing is the right behaviour for a test
            # that is not about throttling.
            return

        decision = await limiter.check(
            f"{scope}:{_client_identifier(request)}",
            limit=attempts,
            window_seconds=window_seconds,
        )

        response.headers["X-RateLimit-Limit"] = str(attempts)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)

        if not decision.allowed:
            # Repeated on the exception: raising discards the `Response`
            # above and builds a fresh one, so headers set there never
            # reach a refused caller — which is exactly the caller who
            # needs to know when to retry.
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many attempts. Please wait "
                    f"{decision.retry_after_seconds} seconds and try again."
                ),
                headers={
                    "Retry-After": str(decision.retry_after_seconds),
                    "X-RateLimit-Limit": str(attempts),
                    "X-RateLimit-Remaining": "0",
                },
            )

    return dependency


def _client_identifier(request: Request) -> str:
    """The address a rate limit is counted against.

    Uses the peer address only, and deliberately **ignores
    `X-Forwarded-For`**. Behind a reverse proxy that header is the real
    client, but it is also caller-supplied: trusting it without a
    trusted-proxy allowlist lets an attacker send a different value on
    every request and bypass the limit entirely — strictly worse than
    having no limit, because it looks like there is one.

    A deployment behind a proxy should configure the ASGI server's
    `--forwarded-allow-ips` (which rewrites `request.client` from a
    header it is told to trust) rather than reading the header here.
    """
    client = request.client
    return client.host if client is not None else "unknown"


def require_permission(
    permission: Permission,
) -> Callable[..., Coroutine[None, None, UserRecord]]:
    """Builds a dependency that admits only callers holding
    `permission`.

    Use as::

        current_user: UserRecord = Depends(
            require_permission(Permission.AUDIT_READ_LEDGER)
        )

    Guards name a *permission* rather than a role so that moving a
    capability between roles is a change to `ROLE_PERMISSIONS` alone,
    never a sweep through every endpoint. The dependency returns the
    same `UserRecord` as `get_current_user`, so a route can require
    authorization without also depending on authentication separately.

    The check itself lives in Layer 3 (`AuthorizationService`); all
    this adds is the translation of its refusal into HTTP.
    """

    async def dependency(
        current_user: UserRecord = Depends(get_current_user),
    ) -> UserRecord:
        role = resolve_role(current_user)
        try:
            _authorization_service.require_permission(role, permission)
        except PermissionDeniedError as exc:
            # 403, never 401: the caller is authenticated, they simply
            # may not do this, and inviting them to re-authenticate
            # could not possibly help.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            ) from exc
        return current_user

    return dependency
