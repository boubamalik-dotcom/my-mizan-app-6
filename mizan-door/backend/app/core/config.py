"""Application configuration loaded from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mizan Door"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mizan_door"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # WARNING: this default is only safe for local development. Always set
    # JWT_SECRET_KEY to a long random value via the environment in any
    # deployed environment - anyone who knows this secret can forge staff
    # login tokens for any clinic.
    jwt_secret_key: str = "dev-insecure-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 hours, ~ one staff shift

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
