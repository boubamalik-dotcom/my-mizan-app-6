"""Layer 2 — authentication dependencies for protecting routes.

This is the seam every other feature's routes (Wallet, Chat, and any
future mini-program endpoint) will `Depends()` on to require an
authenticated caller — exposing that seam is the whole reason this
module exists.
"""
from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
