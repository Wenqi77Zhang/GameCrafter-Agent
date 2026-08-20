"""Project-scoped commands and read models for candidate game knowledge."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from gamecrafter.api.routes.workspace import IdempotencyKey
from gamecrafter.application.agent_review_jobs import REVIEW_KNOWLEDGE_TASK
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
from gamecrafter.infrastructure.database.agent_review_service import (
    AgentReviewConflictError,
    AgentReviewNotFoundError,
    DatabaseAgentReviewService,
)
from gamecrafter.infrastructure.database.conflict_service import (
    ConflictServiceNotFoundError,
    DatabaseConflictService,
)
from gamecrafter.infrastructure.database.knowledge_repository import (
    DatabaseKnowledgeRepository,
)
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
    KnowledgeWorkspaceConflictError,
    KnowledgeWorkspaceNotFoundError,
)
from gamecrafter.infrastructure.database.review_service import (
    DatabaseReviewService,
    ReviewServiceConflictError,
    ReviewServiceNotFoundError,
)
from gamecrafter.infrastructure.database.session import get_session_factory
from gamecrafter.infrastructure.database.snapshot_service import (
    DatabaseSnapshotService,
    SnapshotServiceConflictError,
    SnapshotServiceNotFoundError,
)
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


class KnowledgeAgentReviewCreate(BaseModel):
    extraction_run_id: UUID


class KnowledgeEntityCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("display_name")
    @classmethod
    def name_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display_name must not be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def aliases_must_be_bounded(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 300 for value in values):
            raise ValueError("aliases must contain nonblank values up to 300 characters")
        return values


class KnowledgeEntityCorrection(KnowledgeEntityCreate):
    change_reason: str = Field(min_length=1, max_length=500)

    @field_validator("change_reason")
    @classmethod
    def reason_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("change_reason must not be blank")
        return value


class KnowledgeEntityArchive(BaseModel):
    change_reason: str = Field(min_length=1, max_length=500)

    @field_validator("change_reason")
    @classmethod
    def reason_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("change_reason must not be blank")
        return value


class ClaimReviewCreate(BaseModel):
    decision: Literal["approve", "approve_with_edit", "reject", "defer"]
    approved_value: Any | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class ConflictClosureCreate(BaseModel):
    outcome: Literal["resolved", "dismissed"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class KnowledgeSnapshotCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


@lru_cache
def _repository() -> DatabaseKnowledgeRepository:
    return DatabaseKnowledgeRepository(get_session_factory())


@lru_cache
def _workspace() -> DatabaseWorkspaceService:
    return DatabaseWorkspaceService(get_session_factory())


@lru_cache
def _knowledge_workspace() -> DatabaseKnowledgeWorkspaceService:
    return DatabaseKnowledgeWorkspaceService(get_session_factory())


@lru_cache
def _conflicts() -> DatabaseConflictService:
    return DatabaseConflictService(get_session_factory())


@lru_cache
def _reviews() -> DatabaseReviewService:
    return DatabaseReviewService(get_session_factory())


@lru_cache
def _snapshots() -> DatabaseSnapshotService:
    return DatabaseSnapshotService(get_session_factory())


@lru_cache
def _agent_reviews() -> DatabaseAgentReviewService:
    return DatabaseAgentReviewService(get_session_factory())


def _state_error(error: Exception) -> HTTPException:
    detail = str(error)
    code = status.HTTP_404_NOT_FOUND if "not found" in detail else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=detail)


def _delivery_error(error: Exception) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(error, KnowledgeWorkspaceNotFoundError)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=code, detail=str(error))


def _review_error(error: Exception) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(error, ReviewServiceNotFoundError)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=code, detail=str(error))


def _snapshot_error(error: Exception) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(error, SnapshotServiceNotFoundError)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=code, detail=str(error))


@router.get("/projects/{project_id}/knowledge-entities")
def list_knowledge_entities(
    project_id: UUID,
    include_archived: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    try:
        return {
            "items": _knowledge_workspace().list_entities(
                project_id,
                include_archived=include_archived,
            )
        }
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error


@router.post(
    "/projects/{project_id}/knowledge-entities",
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_entity(
    project_id: UUID,
    command: KnowledgeEntityCreate,
    response: Response,
) -> dict[str, object]:
    try:
        entity, created = _knowledge_workspace().create_entity(
            project_id=project_id,
            display_name=command.display_name,
            aliases=command.aliases,
            actor_id="local-user",
        )
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return entity


@router.put("/projects/{project_id}/knowledge-entities/{entity_id}")
def correct_knowledge_entity(
    project_id: UUID,
    entity_id: UUID,
    command: KnowledgeEntityCorrection,
) -> dict[str, object]:
    try:
        entity, _ = _knowledge_workspace().correct_entity(
            project_id=project_id,
            entity_id=entity_id,
            display_name=command.display_name,
            aliases=command.aliases,
            change_reason=command.change_reason,
            actor_id="local-user",
        )
        return entity
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error


@router.post("/projects/{project_id}/knowledge-entities/{entity_id}/archive")
def archive_knowledge_entity(
    project_id: UUID,
    entity_id: UUID,
    command: KnowledgeEntityArchive,
) -> dict[str, object]:
    try:
        entity, _ = _knowledge_workspace().archive_entity(
            project_id=project_id,
            entity_id=entity_id,
            change_reason=command.change_reason,
            actor_id="local-user",
        )
        return entity
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error


@router.get("/projects/{project_id}/knowledge-entities/{entity_id}/revisions")
def list_knowledge_entity_revisions(
    project_id: UUID,
    entity_id: UUID,
) -> dict[str, object]:
    try:
        return {
            "items": _knowledge_workspace().list_entity_revisions(
                project_id=project_id,
                entity_id=entity_id,
            )
        }
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error


@router.get("/projects/{project_id}/source-versions")
def list_source_versions(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _knowledge_workspace().list_source_versions(project_id)}
    except (KnowledgeWorkspaceNotFoundError, KnowledgeWorkspaceConflictError) as error:
        raise _delivery_error(error) from error


@router.get("/projects/{project_id}/knowledge-extraction-capability")
def get_knowledge_extraction_capability(
    project_id: UUID,
    source_version_id: UUID,
    subject_entity_id: UUID,
) -> dict[str, object]:
    try:
        target = _repository().validate_target(
            project_id=project_id,
            source_version_id=source_version_id,
            subject_entity_id=subject_entity_id,
        )
    except KnowledgeStateError as error:
        raise _state_error(error) from error
    return _replay_capability(get_settings(), target)


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
        completed_run_id = _repository().completed_run_for_target(
            project_id=project_id,
            source_version_id=command.source_version_id,
            subject_entity_id=command.subject_entity_id,
            prompt_version=CLAIM_PROMPT_VERSION,
            schema_version=CLAIM_SCHEMA_VERSION,
        )
        if completed_run_id is not None:
            response.status_code = status.HTTP_200_OK
            return _workspace().get_run(completed_run_id)
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
def list_knowledge_claims(
    project_id: UUID,
    subject_entity_id: UUID | None = None,
    extraction_run_id: UUID | None = None,
) -> dict[str, object]:
    try:
        return {
            "items": _repository().list_claims(
                project_id,
                subject_entity_id=subject_entity_id,
                extraction_run_id=extraction_run_id,
            )
        }
    except KnowledgeStateError as error:
        raise _state_error(error) from error


@router.get("/projects/{project_id}/knowledge-agent-review-capability")
def get_agent_review_capability(project_id: UUID) -> dict[str, object]:
    if get_settings().model_provider != "ollama":
        return {
            "available": False,
            "mode": get_settings().model_provider,
            "reason": "Knowledge Reviewer requires the configured local Ollama model.",
        }
    return {
        "available": True,
        "mode": "local_ollama",
        "reason": "Independent local Knowledge Reviewer is available at zero API cost.",
    }


@router.post("/projects/{project_id}/knowledge-agent-reviews", status_code=202)
def create_agent_review(
    project_id: UUID,
    command: KnowledgeAgentReviewCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    extraction_run_id = command.extraction_run_id
    if get_settings().model_provider != "ollama":
        raise HTTPException(status_code=409, detail="local Ollama reviewer is not configured")
    try:
        _agent_reviews().candidates(project_id=project_id, extraction_run_id=extraction_run_id)
        completed = _agent_reviews().completed_run(
            project_id=project_id, extraction_run_id=extraction_run_id
        )
        if completed is not None:
            response.status_code = status.HTTP_200_OK
            return _workspace().get_run(completed)
        run, created = _workspace().enqueue(
            project_id=project_id,
            idempotency_key=idempotency_key,
            task_type=REVIEW_KNOWLEDGE_TASK,
            payload={"extraction_run_id": str(extraction_run_id)},
            actor_id="local-user",
        )
    except (AgentReviewNotFoundError, AgentReviewConflictError) as error:
        code = 404 if isinstance(error, AgentReviewNotFoundError) else 409
        raise HTTPException(status_code=code, detail=str(error)) from error
    except (WorkspaceNotFoundError, WorkspaceConflictError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


@router.get("/projects/{project_id}/knowledge-agent-reviews")
def get_agent_review(project_id: UUID, extraction_run_id: UUID) -> dict[str, object]:
    try:
        return _agent_reviews().get_summary(
            project_id=project_id, extraction_run_id=extraction_run_id
        )
    except AgentReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/projects/{project_id}/knowledge-agent-reviews/confirm")
def confirm_agent_review_pack(
    project_id: UUID,
    command: KnowledgeAgentReviewCreate,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    extraction_run_id = command.extraction_run_id
    try:
        return _agent_reviews().confirm_pack(
            project_id=project_id,
            extraction_run_id=extraction_run_id,
            command_key=idempotency_key,
            actor_id="local-user",
        )
    except (AgentReviewNotFoundError, AgentReviewConflictError) as error:
        code = 404 if isinstance(error, AgentReviewNotFoundError) else 409
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.post(
    "/projects/{project_id}/knowledge-claims/{claim_id}/reviews",
    status_code=status.HTTP_201_CREATED,
)
def review_knowledge_claim(
    project_id: UUID,
    claim_id: UUID,
    command: ClaimReviewCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        review, created = _reviews().review_claim(
            project_id=project_id,
            claim_id=claim_id,
            decision=command.decision,
            approved_value=command.approved_value,
            reason=command.reason,
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (ReviewServiceNotFoundError, ReviewServiceConflictError) as error:
        raise _review_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return review


@router.get("/projects/{project_id}/knowledge-reviews")
def list_knowledge_reviews(
    project_id: UUID,
    claim_id: UUID | None = None,
    subject_entity_id: UUID | None = None,
) -> dict[str, object]:
    try:
        return {
            "items": _reviews().list_reviews(
                project_id,
                claim_id=claim_id,
                subject_entity_id=subject_entity_id,
            )
        }
    except (ReviewServiceNotFoundError, ReviewServiceConflictError) as error:
        raise _review_error(error) from error


@router.post("/projects/{project_id}/knowledge-conflicts/reconcile")
def reconcile_knowledge_conflicts(project_id: UUID) -> dict[str, object]:
    """Run deterministic comparison without a model call or automatic resolution."""

    try:
        return _conflicts().reconcile(project_id=project_id, actor_id="local-user")
    except ConflictServiceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/projects/{project_id}/knowledge-conflicts")
def list_knowledge_conflicts(
    project_id: UUID,
    status_filter: Annotated[
        Literal["open", "resolved", "dismissed"] | None,
        Query(alias="status"),
    ] = None,
    subject_entity_id: UUID | None = None,
) -> dict[str, object]:
    try:
        return {
            "items": _conflicts().list_conflicts(
                project_id,
                status=status_filter,
                subject_entity_id=subject_entity_id,
            )
        }
    except ConflictServiceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/projects/{project_id}/knowledge-conflicts/{conflict_group_id}/closure",
    status_code=status.HTTP_201_CREATED,
)
def close_knowledge_conflict(
    project_id: UUID,
    conflict_group_id: UUID,
    command: ConflictClosureCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        closure, created = _reviews().close_conflict(
            project_id=project_id,
            conflict_group_id=conflict_group_id,
            outcome=command.outcome,
            reason=command.reason,
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (ReviewServiceNotFoundError, ReviewServiceConflictError) as error:
        raise _review_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return closure


@router.get("/projects/{project_id}/knowledge-snapshot-readiness")
def get_knowledge_snapshot_readiness(project_id: UUID) -> dict[str, object]:
    try:
        return _snapshots().readiness(project_id)
    except (SnapshotServiceNotFoundError, SnapshotServiceConflictError) as error:
        raise _snapshot_error(error) from error


@router.post(
    "/projects/{project_id}/knowledge-snapshots",
    status_code=status.HTTP_201_CREATED,
)
def publish_knowledge_snapshot(
    project_id: UUID,
    command: KnowledgeSnapshotCreate,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> dict[str, object]:
    try:
        snapshot, created = _snapshots().publish(
            project_id=project_id,
            notes=command.notes,
            actor_id="local-user",
            command_key=idempotency_key,
        )
    except (SnapshotServiceNotFoundError, SnapshotServiceConflictError) as error:
        raise _snapshot_error(error) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return snapshot


@router.get("/projects/{project_id}/knowledge-snapshots")
def list_knowledge_snapshots(project_id: UUID) -> dict[str, object]:
    try:
        return {"items": _snapshots().list_snapshots(project_id)}
    except (SnapshotServiceNotFoundError, SnapshotServiceConflictError) as error:
        raise _snapshot_error(error) from error


@router.get("/projects/{project_id}/knowledge-snapshots/{snapshot_id}")
def get_knowledge_snapshot(project_id: UUID, snapshot_id: UUID) -> dict[str, object]:
    try:
        return _snapshots().get_snapshot(project_id=project_id, snapshot_id=snapshot_id)
    except (SnapshotServiceNotFoundError, SnapshotServiceConflictError) as error:
        raise _snapshot_error(error) from error


def _preflight_replay(settings: Settings, target: ExtractionTarget) -> None:
    capability = _replay_capability(settings, target)
    if not capability["available"]:
        raise KnowledgeStateError(str(capability["reason"]))


def _replay_capability(settings: Settings, target: ExtractionTarget) -> dict[str, object]:
    if settings.model_provider == "disabled":
        return {
            "available": False,
            "mode": "disabled",
            "reason_code": "provider_disabled",
            "reason": "knowledge extraction is disabled; configure an exact local replay fixture",
        }
    if settings.model_provider == "ollama":
        return {
            "available": True,
            "mode": "local_ollama",
            "reason_code": "ollama_available",
            "reason": (
                f"local Ollama model {settings.ollama_model} is configured with zero API cost"
            ),
        }
    path = settings.model_replay_fixture_path
    if path is None:
        return {
            "available": False,
            "mode": "offline_replay",
            "reason_code": "fixture_missing",
            "reason": "replay mode has no local fixture configured",
        }
    try:
        loaded = load_replay_fixture(path)
    except InvalidReplayFixtureError:
        return {
            "available": False,
            "mode": "offline_replay",
            "reason_code": "fixture_invalid",
            "reason": "the configured local replay fixture is invalid",
        }

    document = loaded.document
    if (
        document.source_version_id != target.source_version_id
        or document.subject_entity_key != target.subject_entity_key
        or document.locale != target.locale
        or document.region != target.region
        or sha256(document.normalized_text.encode("utf-8")).hexdigest() != target.object_sha256
    ):
        return {
            "available": False,
            "mode": "offline_replay",
            "reason_code": "target_mismatch",
            "reason": "the local replay fixture does not match this extraction target",
        }

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
        return {
            "available": False,
            "mode": "offline_replay",
            "reason_code": "fixture_incomplete",
            "reason": "the local replay fixture does not cover every deterministic text chunk",
        }
    return {
        "available": True,
        "mode": "offline_replay",
        "reason_code": "available",
        "reason": "an exact local zero-cost replay is available",
    }
