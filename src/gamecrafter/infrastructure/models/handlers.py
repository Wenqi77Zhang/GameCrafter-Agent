"""Composition helpers for strict zero-cost knowledge extraction."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import JobHandler
from gamecrafter.application.knowledge_jobs import (
    EXTRACT_KNOWLEDGE_TASK,
    KnowledgeExtractionHandlers,
)
from gamecrafter.application.ports.model_gateway import ModelGateway
from gamecrafter.config.settings import Settings
from gamecrafter.infrastructure.database.knowledge_repository import (
    DatabaseKnowledgeRepository,
)
from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport
from gamecrafter.infrastructure.models.gateways import (
    DisabledModelGateway,
    OllamaLocalGateway,
    ReplayModelGateway,
)
from gamecrafter.infrastructure.models.replay_fixtures import load_replay_fixture
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def build_knowledge_handlers(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    gateway: ModelGateway | None = None,
) -> Mapping[str, JobHandler]:
    """Build the extraction handler without constructing any paid provider client."""

    if gateway is None:
        gateway = _configured_gateway(settings)
    handlers = KnowledgeExtractionHandlers(
        repository=DatabaseKnowledgeRepository(
            session_factory,
            actor_id=settings.worker_id,
        ),
        object_storage=LocalObjectStorage(settings.object_storage_path),
        gateway=gateway,
        document_max_bytes=settings.knowledge_document_max_bytes,
    )
    return {EXTRACT_KNOWLEDGE_TASK: handlers.extract}


def _configured_gateway(settings: Settings) -> ModelGateway:
    if settings.model_provider == "disabled":
        return DisabledModelGateway()
    if settings.model_provider == "ollama":
        return OllamaLocalGateway(
            model=settings.ollama_model,
            requester=OllamaLoopbackTransport(
                base_url=str(settings.ollama_base_url),
                timeout_seconds=settings.ollama_timeout_seconds,
            ),
        )
    path = settings.model_replay_fixture_path
    if path is None:
        raise ValueError("replay mode requires GAMECRAFTER_MODEL_REPLAY_FIXTURE_PATH")
    loaded = load_replay_fixture(path)
    return ReplayModelGateway(loaded.fixtures)
