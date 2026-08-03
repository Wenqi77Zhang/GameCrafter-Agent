"""Project-scoped commands and read models for candidate game knowledge."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.application.knowledge_jobs import EXTRACT_KNOWLEDGE_TASK
from gamecrafter.application.ports.knowledge_repository import (
    ExtractionTarget,
    KnowledgeStateError,
)
from gamecrafter.application.ports.model_gateway import (
    CLAIM_PROMPT_VERSION,
    CLAIM_SCHEMA_VERSION,
    ClaimExtractionRequest,
)
from gamecrafter.application.text_chunking import DeterministicTextChunker
from gamecrafter.config.settings import Settings, get_settings
from gamecrafter.infrastructure.database.knowledge_repository import (
    DatabaseKnowledgeRepository,
)
from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.database.workspace_service import (
    DatabaseWorkspaceService,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
)
from gamecrafter.infrastructure.models.replay_fixtures import (
    InvalidReplayFixtureError,
    load_replay_fixture,
)

router = APIRouter(prefix="/api", tags=["knowledge"])


class KnowledgeExtractionCreate(BaseModel):
    source_version_id: UUID
    subject_entity_id: UUID


@lru_cache
def _repository() -> DatabaseKnowledgeRepository:
    return DatabaseKnowledgeRepository(get_session_factory())


@lru_cache
def _workspace() -> DatabaseWorkspaceService:
    return DatabaseWorkspaceService(get_session_factory())


def _state_error(error: Exception) -> HTTPException:
    detail = str(error)
    code = status.HTTP_404_NOT_FOUND if "not found" in detail else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=detail)


@router.post("/projects/{project_id}/knowledge-extractions", status_code=202)
def create_knowledge_extraction(
    project_id: UUID,
    command: KnowledgeExtractionCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    """Queue extraction only when an exact, local, zero-cost replay can run."""

    try:
        target = _repository().validate_target(
            project_id=project_id,
            source_version_id=command.source_version_id,
            subject_entity_id=command.subject_entity_id,
        )
        _preflight_replay(get_settings(), target)
        run, created = _workspace().enqueue(
            project_id=project_id,
            idempotency_key=idempotency_key,
            task_type=EXTRACT_KNOWLEDGE_TASK,
            payload={
                "source_version_id": str(command.source_version_id),
                "subject_entity_id": str(command.subject_entity_id),
            },
            actor_id="local-user",
        )
    except KnowledgeStateError as error:
        raise _state_error(error) from error
    except WorkspaceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WorkspaceConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.get("/projects/{project_id}/knowledge-extractions/{run_id}")
def get_knowledge_extraction(project_id: UUID, run_id: UUID) -> dict[str, object]:
    try:
        return _repository().extraction_result(project_id=project_id, run_id=run_id)
    except KnowledgeStateError as error:
        raise _state_error(error) from error


@router.get("/projects/{project_id}/knowledge-claims")
def list_knowledge_claims(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _repository().list_claims(project_id)}
    except KnowledgeStateError as error:
        raise _state_error(error) from error


def _preflight_replay(settings: Settings, target: ExtractionTarget) -> None:
    if settings.model_provider == "disabled":
        raise KnowledgeStateError(
            "knowledge extraction is disabled; configure an exact local replay fixture"
        )
    path = settings.model_replay_fixture_path
    if path is None:
        raise KnowledgeStateError("replay mode has no local fixture path configured")
    try:
        loaded = load_replay_fixture(path)
    except InvalidReplayFixtureError as error:
        raise KnowledgeStateError("the configured local replay fixture is invalid") from error

    document = loaded.document
    if (
        document.source_version_id != target.source_version_id
        or document.subject_entity_key != target.subject_entity_key
        or document.locale != target.locale
        or document.region != target.region
        or sha256(document.normalized_text.encode("utf-8")).hexdigest() != target.object_sha256
    ):
        raise KnowledgeStateError("the local replay fixture does not match this extraction target")

    chunks = DeterministicTextChunker().split(document.normalized_text)
    fingerprints = {
        ClaimExtractionRequest(
            source_version_id=document.source_version_id,
            subject_entity_key=document.subject_entity_key,
            text=chunk.text,
            text_start_offset=chunk.start_offset,
            locale=document.locale,
            region=document.region,
            prompt_version=CLAIM_PROMPT_VERSION,
            schema_version=CLAIM_SCHEMA_VERSION,
        ).fingerprint_sha256
        for chunk in chunks
    }
    if fingerprints != set(loaded.fixtures):
        raise KnowledgeStateError(
            "the local replay fixture does not cover every deterministic text chunk"
        )
