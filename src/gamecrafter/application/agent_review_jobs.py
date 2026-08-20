"""Durable orchestration for the independent Knowledge Reviewer Agent."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from gamecrafter.application.jobs import ClaimedJob, TerminalJobError
from gamecrafter.application.ports.agent_review_repository import (
    AgentReviewRepository,
    AgentReviewStateError,
)
from gamecrafter.application.ports.model_gateway import ModelGatewayError
from gamecrafter.application.ports.review_gateway import (
    AgentClaimDecision,
    KnowledgeReviewGateway,
    KnowledgeReviewRequest,
)

REVIEW_KNOWLEDGE_TASK = "knowledge.review"


class KnowledgeReviewHandlers:
    def __init__(self, *, service: AgentReviewRepository, gateway: KnowledgeReviewGateway) -> None:
        self._service = service
        self._gateway = gateway

    def review(self, job: ClaimedJob) -> None:
        try:
            extraction_run_id = _payload(job.payload)
            project_id = self._service.project_id_for_run(job.run_id)
            if (
                self._service.completed_run(
                    project_id=project_id, extraction_run_id=extraction_run_id
                )
                is not None
            ):
                return
            subject_key, candidates = self._service.candidates(
                project_id=project_id, extraction_run_id=extraction_run_id
            )
            decisions: list[AgentClaimDecision] = []
            fingerprints: list[str] = []
            provider = ""
            model = ""
            input_tokens = output_tokens = total_tokens = 0
            pending = [candidates[offset : offset + 8] for offset in range(0, len(candidates), 8)]
            while pending:
                batch = pending.pop(0)
                request = KnowledgeReviewRequest(
                    extraction_run_id=extraction_run_id,
                    subject_entity_key=subject_key,
                    candidates=batch,
                )
                try:
                    result = self._gateway.review(request)
                except ModelGatewayError:
                    if len(batch) == 1:
                        raise
                    midpoint = len(batch) // 2
                    pending[0:0] = [batch[:midpoint], batch[midpoint:]]
                    continue
                provider, model = result.provider, result.model
                fingerprints.append(result.request_fingerprint_sha256)
                decisions.extend(result.decisions)
                input_tokens += result.usage.input_tokens
                output_tokens += result.usage.output_tokens
                total_tokens += result.usage.total_tokens
            self._service.persist(
                run_id=job.run_id,
                project_id=project_id,
                extraction_run_id=extraction_run_id,
                provider=provider,
                model=model,
                fingerprints=tuple(fingerprints),
                decisions=tuple(decisions),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
        except (ModelGatewayError, AgentReviewStateError) as error:
            raise TerminalJobError(f"knowledge review stopped ({type(error).__name__})") from None


def _payload(payload: Mapping[str, Any]) -> UUID:
    if set(payload) != {"extraction_run_id"}:
        raise TerminalJobError("knowledge review payload has unsupported fields")
    try:
        return UUID(str(payload["extraction_run_id"]))
    except (TypeError, ValueError):
        raise TerminalJobError("knowledge review extraction ID must be a UUID") from None
