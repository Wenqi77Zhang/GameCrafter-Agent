"""Validated environment settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings use a project-specific prefix to avoid global collisions."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GAMECRAFTER_",
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"] = "INFO"
    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8000, ge=1, le=65535)
    web_origin: HttpUrl = HttpUrl("http://localhost:5173")
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://gamecrafter:gamecrafter_local@127.0.0.1:5432/gamecrafter"
    )
    object_storage_path: Path = Path("data/objects")
    source_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    source_html_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    source_image_max_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    source_max_images_per_page: int = Field(default=8, ge=0, le=20)
    source_max_redirects: int = Field(default=3, ge=0, le=10)
    source_min_interval_seconds: float = Field(default=1.0, ge=0)
    source_max_concurrency_per_host: int = Field(default=1, ge=1, le=3)
    source_global_max_concurrency: int = Field(default=3, ge=1, le=3)
    source_quick_candidate_limit: int = Field(default=30, ge=1, le=100)
    source_targeted_candidate_limit: int = Field(default=100, ge=1, le=100)
    worker_id: str = "local-worker"
    worker_poll_seconds: float = 1.0
    job_lease_seconds: int = 60
    model_provider: Literal["disabled", "replay", "ollama"] = "disabled"
    model_replay_fixture_path: Path | None = None
    ollama_base_url: HttpUrl = HttpUrl("http://127.0.0.1:11434")
    ollama_model: str = Field(default="qwen3.5:4b", min_length=1, max_length=120)
    ollama_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    knowledge_document_max_bytes: int = Field(default=2 * 1024 * 1024, gt=0)
    trend_connector_timeout_seconds: float = Field(default=45.0, gt=0, le=60)
    trend_connector_max_bytes: int = Field(default=2 * 1024 * 1024, gt=0, le=10 * 1024 * 1024)
    youtube_api_key: SecretStr | None = None
    auth_enabled: bool = False
    auth_cookie_secure: bool = False
    auth_session_hours: int = Field(default=168, ge=1, le=24 * 30)
    quota_projects_per_user: int = Field(default=10, ge=1, le=1000)
    quota_team_members: int = Field(default=20, ge=1, le=1000)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings snapshot per process."""

    return Settings()
