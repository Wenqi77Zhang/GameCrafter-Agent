"""Evidence-bound script generation, quality, review, and export APIs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from gamecrafter.api.routes.identity import request_actor_id
from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.infrastructure.database.script_service import (
    DatabaseScriptService,
    ScriptServiceConflictError,
    ScriptServiceNotFoundError,
)
from gamecrafter.infrastructure.database.session import get_session_factory

router = APIRouter(prefix="/api", tags=["scripts"])


class ScriptRunCreate(BaseModel):
    marketing_task_id: UUID
    revision_budget: int = Field(default=2, ge=0, le=5)
    score_threshold: int = Field(default=80, ge=1, le=100)


class ScriptEditCreate(BaseModel):
    content: dict[str, Any]


class ScriptFinalReviewCreate(BaseModel):
    version_id: UUID
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class ScriptExportCreate(BaseModel):
    version_id: UUID
    format: Literal["markdown", "json"]


@lru_cache
def _service() -> DatabaseScriptService:
    return DatabaseScriptService(get_session_factory())


def _error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND
        if isinstance(error, ScriptServiceNotFoundError)
        else status.HTTP_409_CONFLICT,
        detail=str(error),
    )


def _created(response: Response, created: bool) -> None:
    if not created:
        response.status_code = status.HTTP_200_OK


@router.post("/projects/{project_id}/script-runs", status_code=status.HTTP_201_CREATED)
def create_script_run(
    project_id: UUID,
    command: ScriptRunCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().create_run(
            project_id=project_id,
            **command.model_dump(),
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.get("/projects/{project_id}/script-runs")
def list_script_runs(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _service().list_runs(project_id)}
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/versions/generate",
    status_code=status.HTTP_201_CREATED,
)
def generate_script(
    project_id: UUID, run_id: UUID, idempotency_key: IdempotencyKey, response: Response
) -> dict[str, object]:
    try:
        item, created = _service().generate(
            project_id=project_id,
            run_id=run_id,
            actor_id="local-system",
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/versions/edit", status_code=status.HTTP_201_CREATED
)
def edit_script(
    project_id: UUID,
    run_id: UUID,
    command: ScriptEditCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().edit(
            project_id=project_id,
            run_id=run_id,
            content=command.content,
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/versions/{version_id}/evaluations",
    status_code=status.HTTP_201_CREATED,
)
def evaluate_script(
    project_id: UUID,
    run_id: UUID,
    version_id: UUID,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        item, created = _service().evaluate(
            project_id=project_id, run_id=run_id, version_id=version_id, command_key=idempotency_key
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/versions/revise",
    status_code=status.HTTP_201_CREATED,
)
def revise_script(
    project_id: UUID, run_id: UUID, idempotency_key: IdempotencyKey, response: Response
) -> dict[str, object]:
    try:
        item, created = _service().revise(
            project_id=project_id,
            run_id=run_id,
            actor_id="local-system",
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/final-reviews", status_code=status.HTTP_201_CREATED
)
def final_review(
    project_id: UUID,
    run_id: UUID,
    command: ScriptFinalReviewCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
    request: Request,
) -> dict[str, object]:
    try:
        item, created = _service().final_review(
            project_id=project_id,
            run_id=run_id,
            version_id=command.version_id,
            decision=command.decision,
            reason=command.reason,
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item


@router.post(
    "/projects/{project_id}/script-runs/{run_id}/exports", status_code=status.HTTP_201_CREATED
)
def export_script(
    project_id: UUID,
    run_id: UUID,
    command: ScriptExportCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        item, created = _service().export(
            project_id=project_id,
            run_id=run_id,
            version_id=command.version_id,
            format=command.format,
            command_key=idempotency_key,
        )
    except (ScriptServiceNotFoundError, ScriptServiceConflictError) as error:
        raise _error(error) from error
    _created(response, created)
    return item
