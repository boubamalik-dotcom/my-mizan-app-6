"""Tests for the deployment-blocking security configuration.

Every item here previously failed *silently*: a shipped signing key, a
wildcard CORS policy, and a missing limit all let the app start
normally and look healthy. So these assert the loud failure as much as
the correct behaviour — a security control that is absent is worth
less than one that refuses to boot.
"""
from __future__ import annotations

import pytest

from config import Settings


def _settings(**overrides) -> Settings:
    """A `Settings` built from explicit values only.

    `_env_file=None` stops a developer's own `.env` leaking into the
    test and, for instance, supplying the very key a test is asserting
    the absence of.
    """
    return Settings(_env_file=None, **overrides)


class TestJwtSecret:
    def test_there_is_no_shipped_default(self) -> None:
        # A default in the source is a published secret: anyone reading
        # the repository could forge a token for any account.
        assert _settings().jwt_secret_key is None

    def test_production_refuses_to_start_without_one(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            _settings(environment="production").validate_for_startup()

        assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_production_refuses_a_short_one(self) -> None:
        # An HS256 key shorter than the hash output usually means
        # somebody typed a password instead of generating a key.
        with pytest.raises(RuntimeError) as exc_info:
            _settings(
                environment="production", jwt_secret_key="too-short"
            ).validate_for_startup()

        assert "characters" in str(exc_info.value)

    def test_production_accepts_a_proper_one(self) -> None:
        # An explicit CORS list too: production rejects the wildcard
        # default, which is asserted separately below.
        settings = _settings(
            environment="production",
            jwt_secret_key="a" * 32,
            cors_origins="https://app.mizan.app",
        )

        settings.validate_for_startup()

        assert settings.resolved_jwt_secret_key == "a" * 32

    def test_development_gets_a_random_key_rather_than_a_known_one(self) -> None:
        # Random, not a fixed development default: a fixed one is still
        # a published secret the moment somebody deploys without setting
        # ENVIRONMENT.
        secret = _settings(environment="development").resolved_jwt_secret_key

        assert len(secret) >= 32
        assert "insecure" not in secret
        assert "change-me" not in secret

    def test_the_development_key_is_stable_within_a_process(self) -> None:
        # Otherwise a token would fail to verify against the very
        # service that issued it.
        first = _settings(environment="development").resolved_jwt_secret_key
        second = _settings(environment="development").resolved_jwt_secret_key

        assert first == second

    @pytest.mark.parametrize(
        "environment", ["production", "staging", "prod", "anything-else"]
    )
    def test_an_unrecognised_environment_gets_the_strict_treatment(
        self, environment: str
    ) -> None:
        # Failing safe: an unfamiliar value must not be read as
        # "development".
        with pytest.raises(RuntimeError):
            _settings(environment=environment).validate_for_startup()

    @pytest.mark.parametrize("environment", ["development", "dev", "local", "test"])
    def test_known_non_production_environments_stay_permissive(
        self, environment: str
    ) -> None:
        # No key configured and a wildcard CORS policy: both fine
        # locally, both fatal in production.
        _settings(environment=environment).validate_for_startup()


class TestCorsConfiguration:
    def test_defaults_to_a_wildcard_for_local_development(self) -> None:
        assert _settings().allowed_cors_origins == ["*"]

    def test_parses_a_comma_separated_list(self) -> None:
        settings = _settings(
            cors_origins="https://app.mizan.app, https://admin.mizan.app"
        )

        assert settings.allowed_cors_origins == [
            "https://app.mizan.app",
            "https://admin.mizan.app",
        ]
        assert not settings.allows_all_cors_origins

    def test_production_refuses_a_wildcard(self) -> None:
        # Paired with credentialed requests, a wildcard tells the browser
        # that any website may call this API as a signed-in user.
        with pytest.raises(RuntimeError) as exc_info:
            _settings(
                environment="production",
                jwt_secret_key="a" * 32,
                cors_origins="*",
            ).validate_for_startup()

        assert "CORS_ORIGINS" in str(exc_info.value)

    def test_production_accepts_an_explicit_list(self) -> None:
        _settings(
            environment="production",
            jwt_secret_key="a" * 32,
            cors_origins="https://app.mizan.app",
        ).validate_for_startup()

    def test_a_wildcard_among_explicit_origins_still_counts_as_a_wildcard(
        self,
    ) -> None:
        settings = _settings(cors_origins="https://app.mizan.app,*")

        assert settings.allows_all_cors_origins


class TestRateLimitDefaults:
    def test_login_is_limited_more_tightly_than_registration(self) -> None:
        settings = _settings()

        # Login is a password oracle; registration is spam. Both are
        # worth limiting, but not equally.
        assert settings.login_rate_limit_attempts == 5
        assert settings.login_rate_limit_window_seconds == 60
        assert (
            settings.register_rate_limit_attempts
            > settings.login_rate_limit_attempts
        )
