"""Authenticated, privacy-safe local operations diagnostics."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.operations_service import DatabaseOperationsService
from gamecrafter.infrastructure.database.session import get_session_factory

router = APIRouter(prefix="/api/operations", tags=["operations"])


class WorkerStatus(BaseModel):
    status: Literal["healthy", "stale", "missing"]
    last_seen_at: datetime | None
    age_seconds: int | None
    stale_after_seconds: int


class QueueStatus(BaseModel):
    queued: int
    leased: int
    failed: int
    oldest_queued_age_seconds: int | None
    expired_leases: int


class OperationsStatusResponse(BaseModel):
    status: Literal["ready", "attention"]
    database: Literal["connected"]
    worker: WorkerStatus
    queue: QueueStatus
    attention_codes: list[str]
    observed_at: datetime


@router.get("/status", response_model=OperationsStatusResponse)
def operations_status() -> dict[str, object]:
    """Report whether local jobs can actually leave the durable queue."""

    settings = get_settings()
    return DatabaseOperationsService(get_session_factory()).status(
        stale_after_seconds=settings.worker_stale_after_seconds
    )
