"""Application configuration for El Mizan Real Estate."""

import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "El Mizan Real Estate"
    city: str = "Oran"
    api_prefix: str = "/api/v1"
    # Default to SQLite for local bootstrap; override with DATABASE_URL for PostgreSQL
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./el_mizan.db",
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    debug: bool = os.getenv("DEBUG", "true").lower() in {"1", "true", "yes"}


settings = Settings()
