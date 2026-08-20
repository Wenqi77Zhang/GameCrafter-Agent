"""Persistence boundary for the independent Knowledge Reviewer Agent."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from gamecrafter.application.ports.review_gateway import AgentClaimDecision, ReviewCandidate


class AgentReviewStateError(RuntimeError):
    """Raised when the reviewer input or durable state is invalid."""


class AgentReviewRepository(Protocol):
    def project_id_for_run(self, run_id: UUID) -> UUID: ...

    def completed_run(self, *, project_id: UUID, extraction_run_id: UUID) -> UUID | None: ...

    def candidates(
        self, *, project_id: UUID, extraction_run_id: UUID
    ) -> tuple[str, tuple[ReviewCandidate, ...]]: ...

    def persist(
        self,
        *,
        run_id: UUID,
        project_id: UUID,
        extraction_run_id: UUID,
        provider: str,
        model: str,
        fingerprints: tuple[str, ...],
        decisions: tuple[AgentClaimDecision, ...],
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> dict[str, object]: ...
