"""Unit tests for the pure Layer 3 authentication business logic.

No FastAPI, no SQLAlchemy, no database, no network — every test here
runs purely in memory, proving `auth_service.py` is fully testable in
isolation. `passlib`/`PyJWT` themselves do local computation only
(bcrypt hashing, HMAC signing), so this remains true unit testing.
"""
from __future__ import annotations

import time

import jwt
import pytest

from src.layer_3_business.auth.auth_exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
)
from src.layer_3_business.auth.auth_service import AuthService, TokenPayload

SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"


@pytest.fixture
def service() -> AuthService:
    return AuthService(secret_key=SECRET_KEY)


class TestPasswordHashing:
    def test_hash_password_produces_a_bcrypt_hash(self, service: AuthService) -> None:
        hashed = service.hash_password("correct-horse-battery-staple")
        assert hashed.startswith("$2b$")
        assert hashed != "correct-horse-battery-staple"

    def test_hashing_the_same_password_twice_produces_different_hashes(
        self, service: AuthService
    ) -> None:
        # bcrypt salts every hash, so two hashes of the same password
        # must never be identical (this is what makes rainbow-table
        # attacks against stolen hash dumps infeasible).
        first = service.hash_password("correct-horse-battery-staple")
        second = service.hash_password("correct-horse-battery-staple")
        assert first != second

    def test_verify_password_accepts_the_correct_password(
        self, service: AuthService
    ) -> None:
        hashed = service.hash_password("correct-horse-battery-staple")
        assert service.verify_password("correct-horse-battery-staple", hashed) is True

    def test_verify_password_rejects_the_wrong_password(
        self, service: AuthService
    ) -> None:
        hashed = service.hash_password("correct-horse-battery-staple")
        assert service.verify_password("wrong-password", hashed) is False


class TestAuthenticate:
    def test_accepts_matching_credentials(self, service: AuthService) -> None:
        hashed = service.hash_password("s3cret!")
        service.authenticate(plain_password="s3cret!", hashed_password=hashed)  # no raise

    def test_rejects_wrong_password(self, service: AuthService) -> None:
        hashed = service.hash_password("s3cret!")
        with pytest.raises(InvalidCredentialsError):
            service.authenticate(plain_password="wrong", hashed_password=hashed)

    def test_rejects_nonexistent_account_with_the_same_error(
        self, service: AuthService
    ) -> None:
        # No account -> hashed_password is None. Must raise the exact
        # same exception (and therefore, downstream, the exact same
        # HTTP response) as a wrong password, so a caller cannot
        # distinguish "no such email" from "wrong password" and
        # enumerate valid accounts.
        with pytest.raises(InvalidCredentialsError):
            service.authenticate(plain_password="anything", hashed_password=None)

    def test_wrong_password_and_missing_account_produce_identical_errors(
        self, service: AuthService
    ) -> None:
        hashed = service.hash_password("s3cret!")

        wrong_password_error = None
        missing_account_error = None
        try:
            service.authenticate(plain_password="wrong", hashed_password=hashed)
        except InvalidCredentialsError as exc:
            wrong_password_error = str(exc)

        try:
            service.authenticate(plain_password="anything", hashed_password=None)
        except InvalidCredentialsError as exc:
            missing_account_error = str(exc)

        assert wrong_password_error == missing_account_error


class TestAccessTokens:
    def test_create_and_decode_round_trips_the_subject(
        self, service: AuthService
    ) -> None:
        token = service.create_access_token(subject="alice@example.com")
        payload = service.decode_access_token(token)

        assert isinstance(payload, TokenPayload)
        assert payload.subject == "alice@example.com"
        assert payload.expires_at > payload.issued_at

    def test_additional_claims_are_embedded(self, service: AuthService) -> None:
        token = service.create_access_token(
            subject="alice@example.com", additional_claims={"role": "admin"}
        )
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        assert decoded["role"] == "admin"

    def test_decode_rejects_a_tampered_token(self, service: AuthService) -> None:
        token = service.create_access_token(subject="alice@example.com")
        tampered = token[:-4] + "abcd"
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(tampered)

    def test_decode_rejects_a_token_signed_with_a_different_secret(
        self, service: AuthService
    ) -> None:
        other_service = AuthService(secret_key="a-completely-different-secret-key!!")
        token = other_service.create_access_token(subject="alice@example.com")
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(token)

    def test_decode_rejects_an_expired_token(self) -> None:
        short_lived_service = AuthService(
            secret_key=SECRET_KEY, access_token_expire_minutes=0
        )
        token = short_lived_service.create_access_token(subject="alice@example.com")
        time.sleep(1.1)  # ensure the expiry timestamp (second resolution) has passed

        with pytest.raises(InvalidTokenError, match="expired"):
            short_lived_service.decode_access_token(token)

    def test_decode_rejects_garbage_input(self, service: AuthService) -> None:
        with pytest.raises(InvalidTokenError):
            service.decode_access_token("not-a-real-jwt-at-all")

    def test_decode_rejects_a_token_missing_the_subject_claim(
        self, service: AuthService
    ) -> None:
        # Craft a token that is validly signed but omits "sub".
        malformed_token = jwt.encode(
            {"iat": 0, "exp": 9999999999}, SECRET_KEY, algorithm="HS256"
        )
        with pytest.raises(InvalidTokenError):
            service.decode_access_token(malformed_token)
