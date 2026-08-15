"""Project-scoped zero-cost marketing task, trend, fit, and topic-review APIs."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.infrastructure.database.marketing_service import (
    DatabaseMarketingService,
    MarketingServiceConflictError,
    MarketingServiceNotFoundError,
)
from gamecrafter.infrastructure.database.session import get_session_factory

router = APIRouter(prefix="/api", tags=["marketing"])


class MarketingTaskCreate(BaseModel):
    knowledge_snapshot_id: UUID
    platform: str = Field(min_length=1, max_length=80)
    markets: list[str] = Field(min_length=1, max_length=20)
    audience: str = Field(min_length=1, max_length=500)
    goal: str = Field(min_length=1, max_length=500)
    output_language: str = Field(min_length=1, max_length=40)
    duration_seconds: int = Field(ge=5, le=180)

    @field_validator("platform", "audience", "goal", "output_language")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class TrendSignalCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=160)
    source_url: str = Field(min_length=1, max_length=2048)
    observed_at: datetime
    region: str = Field(min_length=1, max_length=80)
    signal_type: Literal["hashtag", "sound", "topic", "search"]
    title: str = Field(min_length=1, max_length=300)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    metric_name: str | None = Field(default=None, max_length=120)
    metric_value: float | None = Field(default=None, ge=0, le=10**15)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("source_name", "source_url", "region", "title")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class TopicReviewCreate(BaseModel):
    decision: Literal["approve", "reject", "defer"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


@lru_cache
def _service() -> DatabaseMarketingService:
    return DatabaseMarketingService(get_session_factory())


def _error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_404_NOT_FOUND
            if isinstance(error, MarketingServiceNotFoundError)
            else status.HTTP_409_CONFLICT
        ),
        detail=str(error),
    )


@router.post("/projects/{project_id}/marketing-tasks", status_code=status.HTTP_201_CREATED)
def create_marketing_task(
    project_id: UUID,
    command: MarketingTaskCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        item, created = _service().create_task(
            project_id=project_id,
            **command.model_dump(),
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return item


@router.get("/projects/{project_id}/marketing-tasks")
def list_marketing_tasks(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_tasks(project_id)}
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/trend-signals", status_code=status.HTTP_201_CREATED)
def create_trend_signal(
    project_id: UUID,
    command: TrendSignalCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        item, created = _service().add_signal(
            project_id=project_id,
            **command.model_dump(),
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return item


@router.get("/projects/{project_id}/trend-signals")
def list_trend_signals(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_signals(project_id)}
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/marketing-tasks/{task_id}/topic-analysis")
def analyze_topics(project_id: UUID, task_id: UUID) -> dict[str, object]:
    try:
        return {
            "items": _service().analyze(
                project_id=project_id, task_id=task_id, actor_id="local-system"
            )
        }
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error


@router.get("/projects/{project_id}/marketing-tasks/{task_id}/topic-candidates")
def list_topic_candidates(project_id: UUID, task_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_candidates(project_id=project_id, task_id=task_id)}
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error


@router.post(
    "/projects/{project_id}/marketing-tasks/{task_id}/topic-candidates/{candidate_id}/reviews",
    status_code=status.HTTP_201_CREATED,
)
def review_topic(
    project_id: UUID,
    task_id: UUID,
    candidate_id: UUID,
    command: TopicReviewCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        item, created = _service().review_topic(
            project_id=project_id,
            task_id=task_id,
            candidate_id=candidate_id,
            **command.model_dump(),
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return item
