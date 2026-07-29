"""Human-controlled source workspace and run observability API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.database.workspace_service import (
    DatabaseWorkspaceService,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
)

router = APIRouter(prefix="/api", tags=["workspace"])

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


@lru_cache
def _service() -> DatabaseWorkspaceService:
    return DatabaseWorkspaceService(get_session_factory())


class ProjectCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=160)
    default_locale: Literal["zh-CN", "en"] = "zh-CN"


class DiscoveryCreate(BaseModel):
    mode: Literal["quick", "targeted"] = "quick"
    listing_urls: list[HttpUrl] = Field(min_length=1, max_length=10)
    candidate_limit: int = Field(default=30, ge=1, le=100)
    source_types: list[
        Literal[
            "overview",
            "character",
            "world",
            "gameplay",
            "news",
            "update",
            "event",
            "guide_faq",
            "other",
        ]
    ] = Field(default_factory=list)
    published_from: datetime | None = None
    published_to: datetime | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> DiscoveryCreate:
        if self.mode == "quick" and len(self.listing_urls) != 1:
            raise ValueError("quick discovery accepts exactly one listing URL")
        if (
            self.published_from is not None
            and self.published_to is not None
            and self.published_from > self.published_to
        ):
            raise ValueError("published_from must not be after published_to")
        return self


class SourceImportCreate(BaseModel):
    url: HttpUrl | None = None
    candidate_id: UUID | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> SourceImportCreate:
        if (self.url is None) == (self.candidate_id is None):
            raise ValueError("provide exactly one of url or candidate_id")
        return self


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, WorkspaceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, WorkspaceConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="workspace error",
    )


@router.get("/projects")
def list_projects() -> dict[str, object]:
    return {"items": _service().list_projects()}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(command: ProjectCreate, response: Response) -> dict[str, object]:
    project, created = _service().create_project(
        slug=command.slug,
        name=command.name,
        default_locale=command.default_locale,
        actor_id="local-user",
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return project


@router.get("/projects/{project_id}/sources")
def list_sources(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_sources(project_id)}
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


@router.get("/projects/{project_id}/candidates")
def list_candidates(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_candidates(project_id)}
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_runs(project_id)}
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


@router.post("/projects/{project_id}/source-discoveries", status_code=202)
def create_discovery(
    project_id: UUID,
    command: DiscoveryCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    payload = command.model_dump(mode="json", exclude_none=True)
    payload["listing_urls"] = [str(url) for url in command.listing_urls]
    try:
        run, created = _service().enqueue(
            project_id=project_id,
            idempotency_key=idempotency_key,
            task_type="source.discover",
            payload=payload,
            actor_id="local-user",
        )
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.post("/projects/{project_id}/source-imports", status_code=202)
def create_source_import(
    project_id: UUID,
    command: SourceImportCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    payload = (
        {"url": str(command.url)}
        if command.url is not None
        else {"candidate_id": str(command.candidate_id)}
    )
    try:
        run, created = _service().enqueue(
            project_id=project_id,
            idempotency_key=idempotency_key,
            task_type="source.capture",
            payload=payload,
            actor_id="local-user",
            candidate_id=command.candidate_id,
        )
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: UUID) -> dict[str, object]:
    try:
        return _service().get_run(run_id)
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


def _encode_event(event: dict[str, object]) -> str:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: audit\ndata: {payload}\n\n"


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: UUID,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    try:
        cursor = UUID(last_event_id) if last_event_id else None
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be a UUID") from error
    try:
        first_events, first_terminal = await asyncio.to_thread(
            _service().events_after, run_id, cursor
        )
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error

    async def stream() -> AsyncIterator[str]:
        events = first_events
        terminal = first_terminal
        current = cursor
        while True:
            for event in events:
                current = UUID(str(event["id"]))
                yield _encode_event(event)
            if terminal:
                return
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)
            events, terminal = await asyncio.to_thread(_service().events_after, run_id, current)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
