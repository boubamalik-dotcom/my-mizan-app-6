"""Layer 3 — pure business logic for authentication: password
hashing/verification and JWT issuance/verification.

STRICT RULE: this module must never import FastAPI, Pydantic, or
SQLAlchemy. `passlib` and `PyJWT` are used here because they are
framework-agnostic cryptography/encoding utilities with no web
framework or ORM dependency of their own — using them does not violate
this layer's isolation, the same way `layer_3_business/wallet`
freely uses `decimal.Decimal` from the standard library.

Callers (Layer 2, via Layer 4) are responsible for fetching a user's
stored password hash and persisting a newly-created account; this
module never performs any I/O itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

from .auth_exceptions import InvalidCredentialsError, InvalidTokenError

#: Default signing algorithm for issued JWTs. HMAC-SHA256 is
#: appropriate for a single-service backend where the same secret both
#: signs and verifies tokens; a multi-service deployment issuing
#: tokens other services must verify would instead use an asymmetric
#: algorithm (e.g. RS256).
DEFAULT_JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30

#: The JWT claim name Layer 3 identifies the authenticated principal
#: with — deliberately the user's email rather than their database id,
#: so `AuthController.get_current_user` can resolve it via
#: `UserRepository.get_user_by_email`, the same lookup already used at
#: login, without needing an additional repository method.
SUBJECT_CLAIM = "sub"
EXPIRES_AT_CLAIM = "exp"
ISSUED_AT_CLAIM = "iat"


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """The decoded, validated claims of a JWT access token."""

    subject: str
    issued_at: datetime
    expires_at: datetime


class AuthService:
    """Pure business logic for authentication: password hashing,
    password verification/authentication, and JWT issuance/decoding.

    Every method is a deterministic, side-effect-free function of its
    arguments (aside from time-dependent token expiry) — no database
    access, no network calls, and no mutation of any state outside of
    what it returns.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str = DEFAULT_JWT_ALGORITHM,
        access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    ) -> None:
        """
        Args:
            secret_key: The symmetric key used to sign and verify JWTs.
                Must be kept secret and should be at least 32 bytes of
                high-entropy data in production (see `config.py`).
            algorithm: The JWT signing algorithm.
            access_token_expire_minutes: How long an issued access
                token remains valid.
        """
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # -- Password hashing & verification -------------------------------

    def hash_password(self, plain_password: str) -> str:
        """Hashes `plain_password` with bcrypt, suitable for storing
        in `UserModel.hashed_password`.

        Args:
            plain_password: The user's chosen password, in plaintext.

        Returns:
            A bcrypt hash string safe to persist.
        """
        return self._password_context.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Returns whether `plain_password` matches `hashed_password`.

        Args:
            plain_password: The password supplied at login time.
            hashed_password: The bcrypt hash previously produced by
                `hash_password`.

        Returns:
            `True` if they match, `False` otherwise. Never raises for
            a simple mismatch.
        """
        return self._password_context.verify(plain_password, hashed_password)

    def authenticate(
        self, *, plain_password: str, hashed_password: Optional[str]
    ) -> None:
        """Verifies login credentials, raising `InvalidCredentialsError`
        uniformly whether the account does not exist at all
        (`hashed_password` is `None`) or the password is simply wrong
        — the caller should never be able to distinguish the two from
        this method's behavior, preventing user enumeration.

        Args:
            plain_password: The password supplied at login time.
            hashed_password: The stored hash for the claimed account,
                or `None` if no such account exists.

        Raises:
            InvalidCredentialsError: If `hashed_password` is `None` or
                does not match `plain_password`.
        """
        if hashed_password is None or not self.verify_password(
            plain_password, hashed_password
        ):
            raise InvalidCredentialsError()

    # -- JWT issuance & verification --------------------------------------

    def create_access_token(
        self,
        *,
        subject: str,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Issues a signed JWT access token identifying `subject`.

        Args:
            subject: The authenticated principal's identifier —
                conventionally the user's email (see `SUBJECT_CLAIM`).
            additional_claims: Extra claims to embed in the token, if
                any. Must not use the reserved `sub`/`iat`/`exp`
                claim names.

        Returns:
            An encoded, signed JWT string.
        """
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(minutes=self._access_token_expire_minutes)

        payload: Dict[str, Any] = {
            SUBJECT_CLAIM: subject,
            ISSUED_AT_CLAIM: issued_at,
            EXPIRES_AT_CLAIM: expires_at,
        }
        if additional_claims:
            payload.update(additional_claims)

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_access_token(self, token: str) -> TokenPayload:
        """Decodes and validates `token`'s signature and expiry.

        Args:
            token: An encoded JWT, as issued by `create_access_token`.

        Returns:
            The token's validated `TokenPayload`.

        Raises:
            InvalidTokenError: If `token` is malformed, expired, has
                an invalid signature, or is missing a valid subject
                claim.
        """
        try:
            payload = jwt.decode(
                token, self._secret_key, algorithms=[self._algorithm]
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("The access token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError("The access token is invalid.") from exc

        subject = payload.get(SUBJECT_CLAIM)
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError(
                "The access token is missing a valid subject claim."
            )

        issued_at_timestamp = payload.get(ISSUED_AT_CLAIM)
        expires_at_timestamp = payload.get(EXPIRES_AT_CLAIM)
        if issued_at_timestamp is None or expires_at_timestamp is None:
            raise InvalidTokenError(
                "The access token is missing required timestamp claims."
            )

        return TokenPayload(
            subject=subject,
            issued_at=datetime.fromtimestamp(issued_at_timestamp, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc),
        )
