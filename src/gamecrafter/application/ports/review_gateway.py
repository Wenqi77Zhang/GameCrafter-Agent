"""Provider-neutral boundary for independent candidate-claim review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

from gamecrafter.application.ports.model_gateway import ModelTokenUsage

REVIEW_PROMPT_VERSION = "knowledge-review-v3"
REVIEW_SCHEMA_VERSION = "knowledge-review-v1"


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    claim_id: UUID
    predicate: str
    value_kind: str
    value: Any
    evidence_quotes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeReviewRequest:
    extraction_run_id: UUID
    subject_entity_key: str
    candidates: tuple[ReviewCandidate, ...]
    prompt_version: str = REVIEW_PROMPT_VERSION
    schema_version: str = REVIEW_SCHEMA_VERSION

    @property
    def fingerprint_sha256(self) -> str:
        payload = {
            "candidates": [
                {
                    "claim_id": str(item.claim_id),
                    "evidence_quotes": list(item.evidence_quotes),
                    "predicate": item.predicate,
                    "value": item.value,
                    "value_kind": item.value_kind,
                }
                for item in self.candidates
            ],
            "extraction_run_id": str(self.extraction_run_id),
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "subject_entity_key": self.subject_entity_key,
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentClaimDecision:
    claim_id: UUID
    decision: str
    suggested_predicate: str | None
    priority: int
    reason_code: str
    rationale: str
    risk_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeReviewResult:
    provider: str
    model: str
    response_id: str
    request_fingerprint_sha256: str
    decisions: tuple[AgentClaimDecision, ...]
    usage: ModelTokenUsage


class KnowledgeReviewGateway(Protocol):
    def review(self, request: KnowledgeReviewRequest) -> KnowledgeReviewResult:
        """Return one validated independent decision for every supplied claim."""
