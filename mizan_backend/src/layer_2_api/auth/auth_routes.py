"""Layer 2 — Authentication HTTP routes.

Routes are intentionally thin: they parse/validate transport-level
input, delegate to `AuthController`, and return its result as the
appropriate response schema. All business logic and domain-exception
translation lives in `AuthController` — this module must never
contain either.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from config import get_settings

from ...layer_3_business.authz.roles import Role
from ...layer_4_data_access.repositories.user_repository import UserRecord
from .auth_controller import AuthController
from .auth_schemas import (
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from .deps import (
    get_auth_controller,
    get_bearer_token,
    get_current_user,
    rate_limited,
)

#: Read once at import time: the limits are deployment configuration,
#: not per-request state, and `Depends` objects are built when the route
#: is declared.
_settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_response(user: UserRecord) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        # Parsed rather than passed through: an unrecognised stored
        # role is a data-integrity fault and must fail loudly here
        # rather than travel out over the API as an unknown string.
        role=Role.parse(user.role),
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Email already registered."},
        429: {"model": ErrorResponse, "description": "Too many attempts."},
    },
    dependencies=[
        Depends(
            rate_limited(
                scope="register",
                attempts=_settings.register_rate_limit_attempts,
                window_seconds=_settings.register_rate_limit_window_seconds,
            )
        )
    ],
    summary="Register a new user account",
    description=(
        "Creates a new user account. The password is hashed with "
        "bcrypt before being persisted — it is never stored or logged "
        "in plaintext. Returns **400** if the email address is already "
        "registered."
    ),
)
async def register(
    body: RegisterRequest,
    controller: AuthController = Depends(get_auth_controller),
) -> UserResponse:
    """Register a new user account.

    - **email**: A unique, valid email address.
    - **password**: At least 8 characters; hashed with bcrypt before
      storage.
    - **full_name**: The user's display name.
    """
    user = await controller.register(
        email=body.email, password=body.password, full_name=body.full_name
    )
    return _to_user_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid email or password."},
        429: {"model": ErrorResponse, "description": "Too many attempts."},
    },
    dependencies=[
        Depends(
            rate_limited(
                scope="login",
                attempts=_settings.login_rate_limit_attempts,
                window_seconds=_settings.login_rate_limit_window_seconds,
            )
        )
    ],
    summary="Authenticate and obtain a JWT access token",
    description=(
        "Verifies the given email/password against a registered, "
        "active account and, on success, issues a signed JWT bearer "
        "token. Use the returned token in an `Authorization: Bearer "
        "<token>` header to call protected endpoints (see "
        "`GET /auth/me` below, and the Wallet/Chat endpoints in "
        "future). Returns **401** for any invalid combination — "
        "including an unregistered email or a deactivated account — "
        "without revealing which, to prevent account enumeration."
    ),
)
async def login(
    body: LoginRequest,
    controller: AuthController = Depends(get_auth_controller),
) -> TokenResponse:
    """Authenticate and obtain a JWT access token.

    - **email**: The account's email address.
    - **password**: The account's password.
    """
    _user, access_token = await controller.login(email=body.email, password=body.password)
    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid token."}},
    summary="Fetch the authenticated user's profile",
    description=(
        "Returns the profile of the user identified by the bearer "
        "token in the `Authorization` header. Demonstrates — and can "
        "be used to test — the `get_current_user` dependency that "
        "protects this route; the same dependency is intended to "
        "protect the Wallet and Chat routes in a future iteration."
    ),
)
async def get_my_profile(
    current_user: UserRecord = Depends(get_current_user),
) -> UserResponse:
    """Fetch the authenticated user's own profile.

    Requires a valid `Authorization: Bearer <token>` header.
    """
    return _to_user_response(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid token."}},
    summary="Revoke the caller's access token",
    description=(
        "Revokes the bearer token used to make this request, so it "
        "stops working immediately rather than remaining valid until "
        "it expires.\n\n"
        "This matters because a JWT is accepted on the strength of its "
        "signature, not because a server remembers issuing it — so "
        "discarding the client's copy leaves a fully working credential "
        "behind in logs, proxy caches, and browser history. The token's "
        "id is recorded in a shared blocklist for exactly its remaining "
        "lifetime.\n\n"
        "Only this token is affected; the user's other sessions keep "
        "working. Safe to call more than once."
    ),
)
async def logout(
    token: str = Depends(get_bearer_token),
    controller: AuthController = Depends(get_auth_controller),
) -> Response:
    """Revoke the access token presented with this request."""
    await controller.logout(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
