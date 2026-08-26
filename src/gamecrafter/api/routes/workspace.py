"""Human-controlled source workspace and run observability API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gamecrafter.api.routes.identity import identity_service, request_actor_id
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.identity_service import IdentityError
from gamecrafter.infrastructure.database.local_source_service import (
    DatabaseLocalSourceService,
    LocalSourceError,
)
from gamecrafter.infrastructure.database.project_portability import (
    DEFAULT_PORTABLE_ARCHIVE_MAX_BYTES,
    DatabaseProjectPortabilityService,
    ProjectPortabilityError,
)
from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.database.workspace_service import (
    DatabaseWorkspaceService,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

router = APIRouter(prefix="/api", tags=["workspace"])

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


@lru_cache
def _service() -> DatabaseWorkspaceService:
    return DatabaseWorkspaceService(get_session_factory())


@lru_cache
def _local_source_service() -> DatabaseLocalSourceService:
    settings = get_settings()
    return DatabaseLocalSourceService(
        get_session_factory(),
        LocalObjectStorage(settings.object_storage_path),
        max_bytes=settings.knowledge_document_max_bytes,
    )


@lru_cache
def _portability_service() -> DatabaseProjectPortabilityService:
    return DatabaseProjectPortabilityService(
        get_session_factory(), LocalObjectStorage(get_settings().object_storage_path)
    )


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


class LocalSourceCreate(BaseModel):
    document_key: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    kind: Literal["document", "transcript", "gdd"]
    title: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=2_000_000)
    media_type: Literal["text/plain", "text/markdown", "text/vtt", "application/json"]
    locale: str = Field(default="en", min_length=2, max_length=16)
    region: str = Field(default="private", min_length=2, max_length=32)


class ProjectDelete(BaseModel):
    confirmation: str = Field(min_length=8, max_length=100)


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
def list_projects(request: Request) -> dict[str, object]:
    items = _service().list_projects()
    if not get_settings().auth_enabled:
        return {"items": items}
    user = getattr(request.state, "user", None)
    if not user:
        return {"items": []}
    allowed = identity_service().accessible_project_ids(UUID(str(user["id"])))
    return {"items": [item for item in items if str(item["id"]) in allowed]}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    command: ProjectCreate, response: Response, request: Request
) -> dict[str, object]:
    user_id: UUID | None = None
    team_id: UUID | None = None
    if get_settings().auth_enabled:
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="authentication required")
        user_id = UUID(str(user["id"]))
        try:
            identity_service().enforce_project_quota(
                user_id, get_settings().quota_projects_per_user
            )
            team_id = identity_service().default_team_id(user_id)
        except IdentityError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    project, created = _service().create_project(
        slug=command.slug,
        name=command.name,
        default_locale=command.default_locale,
        actor_id=request_actor_id(request),
    )
    if created and user_id is not None and team_id is not None:
        identity_service().assign_project(
            project_id=UUID(str(project["id"])), user_id=user_id, team_id=team_id
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


@router.get("/projects/{project_id}/overview")
def project_overview(project_id: UUID) -> dict[str, object]:
    try:
        return _service().project_overview(project_id)
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


@router.get("/projects/{project_id}/portable-export")
def portable_project_export(project_id: UUID) -> StreamingResponse:
    try:
        filename, payload = _portability_service().export_zip(project_id)
    except ProjectPortabilityError as error:
        code = 404 if "not found" in str(error) else 409
        raise HTTPException(status_code=code, detail=str(error)) from error
    return StreamingResponse(
        iter([payload]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/project-restores", status_code=status.HTTP_201_CREATED)
async def restore_portable_project(request: Request) -> dict[str, object]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/zip":
        raise HTTPException(
            status_code=415, detail="a portable application/zip archive is required"
        )
    owner_user_id: UUID | None = None
    team_id: UUID | None = None
    if get_settings().auth_enabled:
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="authentication required")
        owner_user_id = UUID(str(user["id"]))
        try:
            identity_service().enforce_project_quota(
                owner_user_id, get_settings().quota_projects_per_user
            )
            team_id = identity_service().default_team_id(owner_user_id)
        except IdentityError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    archive = bytearray()
    async for chunk in request.stream():
        archive.extend(chunk)
        if len(archive) > DEFAULT_PORTABLE_ARCHIVE_MAX_BYTES:
            raise HTTPException(status_code=413, detail="project archive exceeds the size limit")
    try:
        return _portability_service().restore_zip(
            bytes(archive), owner_user_id=owner_user_id, team_id=team_id
        )
    except ProjectPortabilityError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, command: ProjectDelete) -> dict[str, object]:
    try:
        return _portability_service().delete_project(
            project_id=project_id, confirmation=command.confirmation
        )
    except ProjectPortabilityError as error:
        code = 404 if "not found" in str(error) else 409
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.post("/projects/{project_id}/source-discoveries", status_code=202)
def create_discovery(
    project_id: UUID,
    command: DiscoveryCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    payload = command.model_dump(mode="json", exclude_none=True)
    payload["listing_urls"] = [str(url) for url in command.listing_urls]
    try:
        run, created = _service().enqueue(
            project_id=project_id,
            idempotency_key=idempotency_key,
            task_type="source.discover",
            payload=payload,
            actor_id=request_actor_id(request),
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
    request: Request,
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
            actor_id=request_actor_id(request),
            candidate_id=command.candidate_id,
        )
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.post("/projects/{project_id}/local-sources", status_code=status.HTTP_201_CREATED)
def create_local_source(
    project_id: UUID,
    command: LocalSourceCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _local_source_service().import_text(
            project_id=project_id,
            **command.model_dump(),
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except LocalSourceError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if "project not found" in str(error)
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return item


@router.get("/runs/{run_id}")
def get_run(run_id: UUID) -> dict[str, object]:
    try:
        return _service().get_run(run_id)
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error


@router.post("/runs/{run_id}/retry")
def retry_run(
    run_id: UUID,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    try:
        run, created = _service().retry_run(
            run_id=run_id,
            command_key=idempotency_key,
            actor_id=request_actor_id(request),
        )
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise _translate_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


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
