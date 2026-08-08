"""Domain-level exceptions for authentication (Layer 3).

These exceptions carry no dependency on any web framework or database
driver. Layer 2 (`auth_controller.py`) is responsible for translating
them into the appropriate HTTP status code.
"""
from __future__ import annotations


class AuthError(Exception):
    """Base class for every error raised by the authentication
    business logic.

    Catching `AuthError` at a call site is guaranteed to catch every
    domain-specific authentication exception below, without needing to
    know the full list of subclasses in advance.
    """


class UserAlreadyExistsError(AuthError):
    """Raised when attempting to register an account for an email
    address that is already registered."""

    def __init__(self, email: str) -> None:
        """
        Args:
            email: The email address that is already registered.
        """
        self.email = email
        super().__init__(f'A user with email "{email}" is already registered.')


class InvalidCredentialsError(AuthError):
    """Raised when a login attempt's email/password combination does
    not match a registered, active account.

    Deliberately carries no information about *why* the attempt
    failed (no such email vs. wrong password vs. inactive account) —
    `AuthService` raises this uniformly for all three cases, since
    revealing which one occurred would let an attacker enumerate valid
    email addresses.
    """

    def __init__(self) -> None:
        """Builds a generic, non-revealing invalid-credentials error."""
        super().__init__("Invalid email or password.")


class InvalidTokenError(AuthError):
    """Raised when a JWT access token is missing, malformed, expired,
    has an invalid signature, or refers to an account that no longer
    exists or is inactive."""

    def __init__(self, reason: str = "The access token is invalid.") -> None:
        """
        Args:
            reason: A short, human-readable explanation of why the
                token was rejected.
        """
        self.reason = reason
        super().__init__(reason)
