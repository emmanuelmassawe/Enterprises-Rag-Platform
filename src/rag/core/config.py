"""Validated runtime settings loaded from environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; defaults are safe for local development."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    app_name: str = Field(default="enterprise-rag-api", min_length=1, max_length=80)
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    metrics_scrape_token: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Accept lowercase env values while preserving strict supported levels."""
        return value.upper() if isinstance(value, str) else value

    @field_validator("metrics_scrape_token", mode="before")
    @classmethod
    def validate_metrics_token(cls, token: object) -> object:
        """Require a strong scrape token when the protected metrics route is enabled."""
        if token == "":
            return None
        value = token.get_secret_value() if isinstance(token, SecretStr) else token
        if isinstance(value, str) and len(value) < 32:
            raise ValueError("METRICS_SCRAPE_TOKEN must contain at least 32 characters")
        return token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so the application uses one validated configuration snapshot."""
    return Settings()
