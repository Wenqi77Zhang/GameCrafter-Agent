"""Private, evidence-bound GDD Studio API."""

from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from gamecrafter.api.routes.identity import request_actor_id
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.gdd_service import DatabaseGddService, GddError
from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

router = APIRouter(prefix="/api/projects/{project_id}/gdd", tags=["gdd-studio"])
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


@lru_cache
def _service() -> DatabaseGddService:
    return DatabaseGddService(
        get_session_factory(), LocalObjectStorage(get_settings().object_storage_path)
    )


class DocumentCreate(BaseModel):
    source_version_id: UUID


class AssumptionCreate(BaseModel):
    chapter_id: UUID | None = None
    statement: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)


class AssumptionDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=1000)


class RevisionCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


def _error(error: GddError) -> HTTPException:
    detail = str(error)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=409, detail=detail)


@router.get("/documents")
def list_documents(project_id: UUID) -> dict[str, object]:
    return {"items": _service().list_documents(project_id)}


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def create_document(
    project_id: UUID, command: DocumentCreate, response: Response, request: Request
) -> dict[str, object]:
    try:
        document, created = _service().create_document(
            project_id=project_id,
            source_version_id=command.source_version_id,
            actor_id=request_actor_id(request),
        )
    except GddError as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return document


@router.get("/documents/{document_id}")
def get_document(project_id: UUID, document_id: UUID) -> dict[str, object]:
    try:
        return _service().get_document(project_id, document_id)
    except GddError as error:
        raise _error(error) from error


@router.post("/documents/{document_id}/assumptions", status_code=status.HTTP_201_CREATED)
def add_assumption(
    project_id: UUID,
    document_id: UUID,
    command: AssumptionCreate,
    response: Response,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    try:
        assumption, created = _service().add_assumption(
            project_id=project_id,
            document_id=document_id,
            chapter_id=command.chapter_id,
            statement=command.statement,
            rationale=command.rationale,
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except GddError as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return assumption


@router.post("/documents/{document_id}/assumptions/{assumption_id}/decision")
def decide_assumption(
    project_id: UUID,
    document_id: UUID,
    assumption_id: UUID,
    command: AssumptionDecision,
    request: Request,
) -> dict[str, object]:
    try:
        return _service().decide_assumption(
            project_id=project_id,
            document_id=document_id,
            assumption_id=assumption_id,
            decision=command.decision,
            reason=command.reason,
            actor_id=request_actor_id(request),
        )
    except GddError as error:
        raise _error(error) from error


@router.post("/documents/{document_id}/revisions", status_code=status.HTTP_201_CREATED)
def approve_revision(
    project_id: UUID,
    document_id: UUID,
    command: RevisionCreate,
    response: Response,
    request: Request,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    try:
        revision, created = _service().approve_revision(
            project_id=project_id,
            document_id=document_id,
            notes=command.notes,
            actor_id=request_actor_id(request),
            command_key=idempotency_key,
        )
    except GddError as error:
        raise _error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return revision
