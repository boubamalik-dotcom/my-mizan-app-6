"""Application configuration for El Mizan Real Estate."""

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "El Mizan Real Estate"
    city: str = "Oran"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/el_mizan"
    openai_api_key: str = ""
    debug: bool = True


settings = Settings()
