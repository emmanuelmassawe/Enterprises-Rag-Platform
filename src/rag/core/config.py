"""Validated runtime settings loaded from environment."""

from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
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
    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    cache_redis_url: SecretStr | None = None
    blob_backend: Literal["local", "s3"] = "local"
    blob_local_root: str = Field(
        default_factory=lambda: str(Path(gettempdir()) / "enterprise-rag-blobs")
    )
    blob_bucket: str = "enterprise-rag-local"
    blob_endpoint_url: str | None = None
    blob_region: str = "us-east-1"
    blob_access_key_id: SecretStr | None = None
    blob_secret_access_key: SecretStr | None = None
    blob_max_upload_bytes: int = Field(default=104_857_600, ge=1_048_576, le=1_073_741_824)
    blob_max_pages: int = Field(default=250, ge=1, le=2_000)
    ingestion_max_queue_size: int = Field(default=500, ge=1, le=100_000)
    ingestion_max_concurrency: int = Field(default=2, ge=1, le=32)
    ingestion_chunk_chars: int = Field(default=2_400, ge=200, le=8_000)
    ingestion_chunk_overlap_chars: int = Field(default=300, ge=0, le=1_000)
    embedding_api_key: SecretStr | None = None
    embedding_model: str = Field(default="gemini-embedding-2", min_length=1, max_length=100)
    embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    embedding_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    generation_model: str = Field(default="gemini-3.8-flash", min_length=1, max_length=100)
    generation_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    generation_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    generation_max_concurrency: int = Field(default=8, ge=1, le=64)
    query_context_token_budget: int = Field(default=6000, ge=256, le=32_000)
    query_minimum_similarity: float = Field(default=0.35, ge=0.0, le=1.0)
    query_cache_ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    rate_limit_requests: int = Field(default=60, ge=1, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    rate_limit_memory_fallback_requests: int = Field(default=10, ge=1, le=10_000)
    rate_limit_memory_fallback_window_seconds: int = Field(default=60, ge=1, le=86_400)
    metrics_scrape_token: SecretStr | None = None

    @model_validator(mode="after")
    def production_requires_shared_dependencies(self) -> Self:
        """Prevent deployment from silently using local blobs or missing ingestion providers."""
        if self.app_env in {"staging", "production"}:
            if self.database_url is None or self.redis_url is None:
                raise ValueError("staging and production require DATABASE_URL and REDIS_URL")
            if self.blob_backend != "s3" or self.blob_bucket == "enterprise-rag-local":
                raise ValueError("staging and production require a named private S3 bucket")
            if self.embedding_api_key is None:
                raise ValueError("staging and production require EMBEDDING_API_KEY")
            if self.blob_endpoint_url and not self.blob_endpoint_url.startswith("https://"):
                raise ValueError("staging and production S3 endpoints must use HTTPS")
        return self

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, level: object) -> object:
        """Accept conventional lowercase environment values while validating the result."""
        return level.upper() if isinstance(level, str) else level

    @field_validator(
        "database_url",
        "migration_database_url",
        "redis_url",
        "cache_redis_url",
        "embedding_api_key",
        "blob_access_key_id",
        "blob_secret_access_key",
        mode="before",
    )
    @classmethod
    def empty_connection_url_is_unset(cls, value: object) -> object:
        """Treat empty local environment variables as unset rather than malformed secrets."""
        return None if value == "" else value

    @field_validator("metrics_scrape_token", mode="before")
    @classmethod
    def validate_metrics_token(cls, token: object) -> object:
        """Require a strong scrape token when the protected metrics route is enabled."""
        if token == "":
            return None
        if isinstance(token, str) and len(token) < 32:
            raise ValueError("METRICS_SCRAPE_TOKEN must contain at least 32 characters")
        if isinstance(token, SecretStr) and len(token.get_secret_value()) < 32:
            raise ValueError("METRICS_SCRAPE_TOKEN must contain at least 32 characters")
        return token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so the application uses one validated configuration snapshot."""
    return Settings()
