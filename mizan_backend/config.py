"""Application-wide configuration.

Centralizes environment-driven settings (database, cache/broker URLs,
etc.) behind a single, strictly-typed `Settings` object so that no
layer reaches into `os.environ` directly. Only `main.py` (composition
root) and the storage/data-access layers that need connection strings
should ever import this module.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strictly-typed environment configuration.

    Values are read from environment variables (or a local `.env`
    file) and validated at startup, so misconfiguration fails fast
    instead of surfacing as an obscure runtime error deep inside a
    request handler.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Mizan Backend"
    environment: str = "development"
    debug: bool = False

    # Layer 5 — storage
    database_url: str = "sqlite+aiosqlite:///./mizan_backend.db"

    #: Whether startup should run `create_all` to build any missing
    #: tables.
    #:
    #: Off by default, and it should stay off anywhere that holds data.
    #: `create_all` only ever *creates* tables that do not exist; it
    #: silently skips tables that do, so it cannot add a column to one
    #: — it would quietly leave a database on an old schema and report
    #: success, which is exactly how `users.role` came to be missing at
    #: runtime. Deployments run `alembic upgrade head` instead.
    #:
    #: Useful for a disposable local database where running migrations
    #: first is friction rather than safety.
    auto_create_schema: bool = False

    # Layer 4 — cache / pub-sub broker
    redis_url: str = "redis://localhost:6379/0"

    # Chat Engine tuning
    chat_message_max_length: int = 4000
    chat_room_max_participants: int = 200
    chat_rate_limit_messages: int = 10
    chat_rate_limit_window_seconds: float = 10.0

    # Authentication — JWT signing
    #: The HMAC key every access token is signed with.
    #:
    #: There is deliberately **no default**. A shipped default is a
    #: published secret: anyone reading this repository could forge a
    #: token for any account, and the failure is silent — the app starts,
    #: logins work, and nothing looks wrong. Leaving it unset instead
    #: produces a loud, specific error at startup in production, and a
    #: random per-process key in development (see
    #: [resolved_jwt_secret_key]).
    #:
    #: Generate one with `openssl rand -hex 32`.
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    #: Shortest secret accepted in production. HS256 keys shorter than
    #: the hash output add no security over a 32-byte one and are
    #: usually a sign someone typed a password rather than generating a
    #: key.
    min_jwt_secret_length: int = 32

    # Authentication — brute-force protection
    #: Login attempts allowed per client IP per window.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    #: Registration is limited too, more loosely: the same endpoint
    #: shape is equally attractive for account-spam.
    register_rate_limit_attempts: int = 10
    register_rate_limit_window_seconds: int = 60

    # HTTP — cross-origin access
    #: Comma-separated origins permitted to call the API from a browser,
    #: or `*` for any.
    #:
    #: `*` is fine locally and **rejected in production**: combined with
    #: `allow_credentials=True` it tells the browser that any site may
    #: make authenticated requests on a signed-in user's behalf, which
    #: is cross-site request forgery by configuration.
    cors_origins: str = "*"

    @property
    def is_production(self) -> bool:
        """Whether this process is running in a production environment.

        Anything that is not explicitly a development or test
        environment counts as production: an unrecognised value should
        get the stricter behaviour, not the laxer one.
        """
        return self.environment.strip().lower() not in {
            "development",
            "dev",
            "local",
            "test",
            "testing",
        }

    @property
    def allowed_cors_origins(self) -> List[str]:
        """[cors_origins] parsed into the list `CORSMiddleware` wants."""
        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
        return origins or ["*"]

    @property
    def allows_all_cors_origins(self) -> bool:
        return "*" in self.allowed_cors_origins

    @property
    def resolved_jwt_secret_key(self) -> str:
        """The signing key to use, or a hard failure explaining why
        there isn't one.

        In production a missing or too-short key raises, so the process
        never starts in a state where its tokens are forgeable.

        Outside production a random key is generated per process. That
        is deliberately *not* a fixed development default: a fixed one
        is still a published secret the moment someone deploys without
        setting `ENVIRONMENT`. The cost is that tokens do not survive a
        restart locally, which is the honest consequence of having
        configured no key.
        """
        configured = (self.jwt_secret_key or "").strip()

        if not configured:
            if self.is_production:
                raise RuntimeError(
                    "JWT_SECRET_KEY is not set. Refusing to start in "
                    f'environment "{self.environment}" without a signing key — '
                    "every issued token would be forgeable. Generate one with "
                    "`openssl rand -hex 32` and set JWT_SECRET_KEY."
                )
            return _ephemeral_development_secret()

        if self.is_production and len(configured) < self.min_jwt_secret_length:
            raise RuntimeError(
                f"JWT_SECRET_KEY is only {len(configured)} characters; "
                f"at least {self.min_jwt_secret_length} are required in "
                f'environment "{self.environment}". Generate one with '
                "`openssl rand -hex 32`."
            )

        return configured

    def validate_for_startup(self) -> None:
        """Fails fast on any configuration that is unsafe to serve
        with.

        Called once by the composition root so a misconfigured
        deployment dies at boot with a specific message, rather than
        starting and quietly being insecure — which is the failure mode
        every item here previously had.
        """
        self.resolved_jwt_secret_key  # raises if missing or too short

        if self.is_production and self.allows_all_cors_origins:
            raise RuntimeError(
                "CORS_ORIGINS is '*' but the environment is "
                f'"{self.environment}". With credentialed requests that '
                "permits any website to call this API as a signed-in user. "
                "Set CORS_ORIGINS to an explicit comma-separated list."
            )


@lru_cache
def _ephemeral_development_secret() -> str:
    """A random signing key for this process only.

    Cached so every caller within one process agrees on it — otherwise
    a token would fail to verify against the very service that issued
    it.
    """
    return secrets.token_hex(32)

    # Authorization — role bootstrap
    #: Emails that receive the `admin` role when they register.
    #:
    #: Solves the bootstrap problem: granting a role requires
    #: `users:manage_roles`, which only an admin holds, so without this
    #: the very first admin could never exist except by editing the
    #: database directly. Set it to the compliance owner's address at
    #: deploy time, e.g.
    #: `BOOTSTRAP_ADMIN_EMAILS=compliance@mizan.app,cto@mizan.app`.
    #:
    #: Empty by default: every account is an ordinary user until
    #: someone deliberately configures otherwise. Matching is
    #: case-insensitive, since email local parts are routinely typed
    #: with inconsistent case.
    bootstrap_admin_emails: str = ""

    def is_bootstrap_admin(self, email: str) -> bool:
        """Whether `email` is configured to be granted `admin` on
        registration."""
        configured = {
            candidate.strip().lower()
            for candidate in self.bootstrap_admin_emails.split(",")
            if candidate.strip()
        }
        return email.strip().lower() in configured


@lru_cache
def get_settings() -> Settings:
    """Returns the process-wide `Settings` singleton.

    Cached with `lru_cache` so environment parsing happens exactly
    once; tests can call `get_settings.cache_clear()` to reload with a
    different environment.
    """
    return Settings()
