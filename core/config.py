from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="sqlite:///./temporal_proj.db",
        description="SQLAlchemy database URL.",
    )
    permits_api_url: str | None = Field(
        default=None,
        description="Optional external permits API endpoint used by ingestion only.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
