"""Service health endpoint."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from gamecrafter import __version__
from gamecrafter.application.agent_catalog import public_agent_catalog
from gamecrafter.config.settings import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Stable health response consumed by the M0 frontend."""

    status: Literal["ok"]
    service: Literal["gamecrafter-api"]
    version: str
    environment: str
    phase: Literal["M13-local"]
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
        phase="M13-local",
        timestamp=datetime.now(UTC),
    )


@router.get("/agents")
async def agents() -> dict[str, object]:
    """Expose the versioned specialist roster without runtime secrets."""

    return {"orchestrator": "durable-harness-v1", "items": public_agent_catalog()}
