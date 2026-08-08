"""Application-wide configuration.

Centralizes environment-driven settings (database, cache/broker URLs,
etc.) behind a single, strictly-typed `Settings` object so that no
layer reaches into `os.environ` directly. Only `main.py` (composition
root) and the storage/data-access layers that need connection strings
should ever import this module.
"""
from __future__ import annotations

from functools import lru_cache

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

    # Layer 4 — cache / pub-sub broker
    redis_url: str = "redis://localhost:6379/0"

    # Chat Engine tuning
    chat_message_max_length: int = 4000
    chat_room_max_participants: int = 200
    chat_rate_limit_messages: int = 10
    chat_rate_limit_window_seconds: float = 10.0

    # Authentication — JWT signing
    #: INSECURE DEVELOPMENT DEFAULT. Production deployments MUST set
    #: the `JWT_SECRET_KEY` environment variable to a high-entropy
    #: secret (e.g. `openssl rand -hex 32`) — every token signed with
    #: this default is forgeable by anyone who reads this source file.
    jwt_secret_key: str = "insecure-development-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

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
