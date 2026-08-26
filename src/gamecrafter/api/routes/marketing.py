"""Project-scoped zero-cost marketing task, trend, fit, and topic-review APIs."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from gamecrafter.api.routes.identity import request_actor_id
from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.marketing_service import (
    DatabaseMarketingService,
    MarketingServiceConflictError,
    MarketingServiceNotFoundError,
)
from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.trends.connectors import ConnectorError, PublicTrendConnector

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


class TrendConnectorSync(BaseModel):
    query: str = Field(min_length=2, max_length=160)
    region: str = Field(default="US", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    max_results: int = Field(default=10, ge=1, le=50)
    lookback_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


@lru_cache
def _service() -> DatabaseMarketingService:
    return DatabaseMarketingService(get_session_factory())


@lru_cache
def _connector() -> PublicTrendConnector:
    settings = get_settings()
    return PublicTrendConnector(
        timeout_seconds=settings.trend_connector_timeout_seconds,
        max_bytes=settings.trend_connector_max_bytes,
    )


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
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().create_task(
            project_id=project_id,
            **command.model_dump(),
            actor_id=request_actor_id(request),
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
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().add_signal(
            project_id=project_id,
            **command.model_dump(),
            actor_id=request_actor_id(request),
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


@router.get("/trend-connectors")
def list_trend_connectors() -> dict[str, object]:
    settings = get_settings()
    return {
        "items": [
            {
                "key": "gdelt-doc",
                "name": "GDELT DOC 2.0",
                "mode": "live_public_api",
                "available": True,
                "requires_secret": False,
                "cost": "zero_paid_api",
            },
            {
                "key": "google-news-rss",
                "name": "Google News RSS",
                "mode": "live_public_rss",
                "available": True,
                "requires_secret": False,
                "cost": "zero_paid_api",
            },
            {
                "key": "youtube-data",
                "name": "YouTube Data API",
                "mode": "official_api_free_quota",
                "available": settings.youtube_api_key is not None,
                "requires_secret": True,
                "cost": "zero_paid_api_quota_limited",
            },
            {
                "key": "tiktok-manual",
                "name": "TikTok Creative Center",
                "mode": "manual_verified_import",
                "available": True,
                "requires_secret": False,
                "cost": "zero_paid_api",
            },
        ]
    }


@router.post("/projects/{project_id}/trend-connectors/{connector_key}/sync")
def sync_trend_connector(
    project_id: UUID,
    connector_key: Literal["gdelt-doc", "google-news-rss", "youtube-data"],
    command: TrendConnectorSync,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    settings = get_settings()
    try:
        if connector_key == "gdelt-doc":
            observations = _connector().gdelt(
                query=command.query,
                region=command.region,
                max_results=command.max_results,
                lookback_hours=command.lookback_hours,
            )
        elif connector_key == "google-news-rss":
            observations = _connector().google_news(
                query=command.query,
                region=command.region,
                max_results=command.max_results,
                lookback_hours=command.lookback_hours,
            )
        else:
            if settings.youtube_api_key is None:
                raise ConnectorError("YouTube connector is not configured")
            observations = _connector().youtube(
                api_key=settings.youtube_api_key.get_secret_value(),
                query=command.query,
                region=command.region,
                max_results=command.max_results,
                published_after=datetime.now(UTC) - timedelta(hours=command.lookback_hours),
            )
        items: list[dict[str, object]] = []
        inserted = 0
        for observation in observations:
            fingerprint = hashlib.sha256(
                f"{idempotency_key}|{connector_key}|{observation.external_id}".encode()
            ).hexdigest()
            item, created = _service().add_signal(
                project_id=project_id,
                source_name=observation.source_name,
                source_url=observation.source_url,
                observed_at=observation.observed_at,
                region=observation.region,
                signal_type=observation.signal_type,
                title=observation.title,
                keywords=list(observation.keywords),
                metric_name=None,
                metric_value=None,
                notes=observation.notes,
                actor_id="marketing.trend_analyst",
                actor_type="system",
                command_key=f"connector-{fingerprint}",
            )
            items.append(item)
            inserted += int(created)
    except ConnectorError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error
    return {
        "connector": connector_key,
        "query": command.query,
        "region": command.region.upper(),
        "synced_at": datetime.now(UTC).isoformat(),
        "fetched": len(observations),
        "inserted": inserted,
        "reused": len(observations) - inserted,
        "items": items,
    }


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
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().review_topic(
            project_id=project_id,
            task_id=task_id,
            candidate_id=candidate_id,
            **command.model_dump(),
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except (MarketingServiceNotFoundError, MarketingServiceConflictError) as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return item
