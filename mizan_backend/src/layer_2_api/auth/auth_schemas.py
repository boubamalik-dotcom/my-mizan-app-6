"""Layer 2 — Pydantic request/response contracts (DTOs) for
authentication.

`EmailStr` (from `pydantic[email]`) validates email format at the API
boundary, before an invalid address ever reaches Layer 3/4.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

#: Minimum acceptable password length. Enforced here (at the API
#: boundary) rather than in Layer 3, since it is a UX/input-shape
#: concern, not a cryptographic one — `AuthService.hash_password`
#: would happily hash a one-character string.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class RegisterRequest(BaseModel):
    """Body for `POST /auth/register`."""

    email: EmailStr = Field(..., description="The new account's unique email address.")
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=f"At least {MIN_PASSWORD_LENGTH} characters.",
    )
    full_name: str = Field(..., min_length=1, max_length=255)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "alice@example.com",
                    "password": "correct-horse-battery-staple",
                    "full_name": "Alice Example",
                }
            ]
        }
    }


class LoginRequest(BaseModel):
    """Body for `POST /auth/login`."""

    email: EmailStr
    password: str = Field(..., min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "alice@example.com",
                    "password": "correct-horse-battery-staple",
                }
            ]
        }
    }


class UserResponse(BaseModel):
    """A user account's public profile — never includes
    `hashed_password`."""

    id: str
    email: str
    full_name: str
    is_active: bool


class TokenResponse(BaseModel):
    """Response body for a successful login: a bearer access token."""

    access_token: str
    token_type: str = "bearer"


class ErrorResponse(BaseModel):
    """Standard error body for every REST endpoint's non-2xx
    responses."""

    detail: str
