"""Non-blocking local-model creative commands and project-scoped progress."""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from gamecrafter.api.routes.identity import request_actor_id
from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.application.creative import CreativeError
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.creative_service import DatabaseCreativeService
from gamecrafter.infrastructure.database.marketing_service import (
    MarketingServiceConflictError,
    MarketingServiceNotFoundError,
)
from gamecrafter.infrastructure.database.script_service import (
    ScriptServiceConflictError,
    ScriptServiceNotFoundError,
)
from gamecrafter.infrastructure.database.session import get_session_factory

router = APIRouter(prefix="/api", tags=["creative"])


class CreativeCommand(BaseModel):
    operation: Literal["strategy", "write", "revise", "critique"]
    target_id: UUID


@lru_cache
def _service():
    return DatabaseCreativeService(get_session_factory(), get_settings())


@router.get("/creative-capability")
def creative_capability():
    return _service().capability()


@router.get("/projects/{project_id}/creative-operations")
def creative_operations(project_id: UUID, target_id: UUID | None = None):
    try:
        return {
            "items": _service().list(project_id, target_id),
            "readiness": _service().readiness(project_id, target_id),
        }
    except ScriptServiceNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except CreativeError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/projects/{project_id}/creative-operations", status_code=202)
def create_creative_operation(
    project_id: UUID,
    command: CreativeCommand,
    idempotency_key: IdempotencyKey,
    request: Request,
    response: Response,
):
    try:
        item, created = _service().enqueue(
            project_id=project_id,
            **command.model_dump(),
            command_key=idempotency_key,
            actor_id=request_actor_id(request),
        )
        if not created:
            response.status_code = 200
        return item
    except (ScriptServiceNotFoundError, MarketingServiceNotFoundError) as error:
        raise HTTPException(404, str(error)) from error
    except (CreativeError, ScriptServiceConflictError, MarketingServiceConflictError) as error:
        raise HTTPException(409, str(error)) from error


@router.post("/projects/{project_id}/creative-operations/{operation_id}/cancel")
def cancel_creative_operation(project_id: UUID, operation_id: UUID, request: Request):
    try:
        return _service().cancel(project_id, operation_id, request_actor_id(request))
    except CreativeError as error:
        raise HTTPException(409, str(error)) from error
