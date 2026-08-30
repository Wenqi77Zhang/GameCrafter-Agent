"""Persistence boundary for durable, evidence-bound knowledge extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from gamecrafter.application.knowledge_extraction import (
    ExtractionObserver,
    ExtractionRunResult,
)


class KnowledgeStateError(ValueError):
    """Raised when extraction targets or durable lineage are inconsistent."""


@dataclass(frozen=True, slots=True)
class ExtractionTarget:
    """Validated project-local source text and subject metadata."""

    project_id: UUID
    source_version_id: UUID
    subject_entity_id: UUID
    subject_entity_key: str
    subject_labels: tuple[str, ...]
    locale: str
    region: str
    object_key: str
    object_sha256: str
    size_bytes: int


class KnowledgeRepository(Protocol):
    """Load immutable inputs and commit one fail-closed extraction result."""

    def validate_target(
        self,
        *,
        project_id: UUID,
        source_version_id: UUID,
        subject_entity_id: UUID,
    ) -> ExtractionTarget:
        """Validate API input before a workflow is enqueued."""

    def target_for_run(
        self,
        *,
        run_id: UUID,
        source_version_id: UUID,
        subject_entity_id: UUID,
    ) -> ExtractionTarget:
        """Validate the same immutable target against one workflow run."""

    def result_exists(self, run_id: UUID) -> bool:
        """Return whether this run already committed its atomic result."""

    def observer(
        self,
        *,
        run_id: UUID,
        target: ExtractionTarget,
        job_attempt: int,
    ) -> ExtractionObserver:
        """Return a redacted per-invocation persistence observer."""

    def persist_result(
        self,
        *,
        run_id: UUID,
        target: ExtractionTarget,
        job_attempt: int,
        normalized_text: str,
        result: ExtractionRunResult,
    ) -> int:
        """Atomically persist claims, evidence, result marker, and audit event."""

    def extraction_result(self, *, project_id: UUID, run_id: UUID) -> dict[str, object]:
        """Return one project-scoped result and its redacted invocation trace."""

    def list_claims(
        self,
        project_id: UUID,
        *,
        subject_entity_id: UUID | None = None,
        extraction_run_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Return immutable candidate claims with exact evidence spans."""
