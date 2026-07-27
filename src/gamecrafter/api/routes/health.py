"""Service health endpoint."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from gamecrafter import __version__
from gamecrafter.config.settings import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Stable health response consumed by the M0 frontend."""

    status: Literal["ok"]
    service: Literal["gamecrafter-api"]
    version: str
    environment: str
    phase: Literal["M1-A"]
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return process health without touching external dependencies."""

    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="gamecrafter-api",
        version=__version__,
        environment=settings.environment,
        phase="M1-A",
        timestamp=datetime.now(UTC),
    )
