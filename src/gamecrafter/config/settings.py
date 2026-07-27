"""Validated environment settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import HttpUrl, SecretStr
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
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: HttpUrl = HttpUrl("http://localhost:5173")
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://gamecrafter:gamecrafter_local@127.0.0.1:5432/gamecrafter"
    )
    data_dir: Path = Path("data")
    worker_id: str = "local-worker"
    worker_poll_seconds: float = 1.0
    job_lease_seconds: int = 60
    model_provider: str = "disabled"
    model_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings snapshot per process."""

    return Settings()
