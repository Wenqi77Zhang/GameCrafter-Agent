"""Loopback-only structured Knowledge Reviewer Agent gateway."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gamecrafter.application.ports.model_gateway import (
    InvalidModelOutputError,
    ModelProviderError,
    ModelTokenUsage,
)
from gamecrafter.application.ports.review_gateway import (
    REVIEW_PROMPT_VERSION,
    REVIEW_SCHEMA_VERSION,
    AgentClaimDecision,
    KnowledgeReviewRequest,
    KnowledgeReviewResult,
)
from gamecrafter.domain.knowledge.claims import FactPredicate

_INSTRUCTIONS = """\
You are an independent evidence auditor, not the extractor.
Review every candidate using only its value, predicate, and exact public-source quotes.
Do not assume a quote supports a semantic category merely because a name appears.
Use agent_approved only for a useful, correctly typed fact directly supported by the quote.
Use agent_rejected for duplicates, forced predicates, unsupported conclusions,
and minor catalog noise.
Use needs_human for genuinely ambiguous but potentially valuable claims.
If the predicate is wrong, set suggested_predicate and do not approve the original claim.
Prefer durable game facts and major patch changes.
Keep no more than the most useful 15 claims overall.
Return one decision for every supplied claim ID and never invent an ID.
Never approve a value by assuming a typical event duration, game convention, or missing context.
If any date, time, number, name, or relationship is absent from the quotes, reject the inference.
"""


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    decision: str = Field(pattern="^(agent_approved|agent_rejected|needs_human)$")
    suggested_predicate: FactPredicate | None = None
    priority: int = Field(ge=0, le=100)
    reason_code: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=1, max_length=300)
    risk_codes: list[str] = Field(max_length=8)


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[_Decision] = Field(min_length=1, max_length=8)


class OllamaKnowledgeReviewerGateway:
    def __init__(self, *, model: str, requester: Any) -> None:
        self._model = model
        self._requester = requester

    def review(self, request: KnowledgeReviewRequest) -> KnowledgeReviewResult:
        if request.prompt_version != REVIEW_PROMPT_VERSION:
            raise InvalidModelOutputError("unsupported review prompt version")
        if request.schema_version != REVIEW_SCHEMA_VERSION:
            raise InvalidModelOutputError("unsupported review schema version")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _INSTRUCTIONS},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "subject_entity_key": request.subject_entity_key,
                            "candidates": [
                                {
                                    "claim_id": str(item.claim_id),
                                    "predicate": item.predicate,
                                    "value_kind": item.value_kind,
                                    "value": item.value,
                                    "evidence_quotes": list(item.evidence_quotes),
                                }
                                for item in request.candidates
                            ],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                },
            ],
            "stream": False,
            "think": False,
            "format": _Envelope.model_json_schema(),
            "options": {"temperature": 0, "num_predict": 1800},
        }
        try:
            response = self._requester(payload)
        except Exception as error:
            raise ModelProviderError(
                f"local reviewer request failed ({type(error).__name__})"
            ) from error
        message = response.get("message") if isinstance(response, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str) or not content.strip():
            raise InvalidModelOutputError("reviewer returned no structured output")
        try:
            envelope = _Envelope.model_validate_json(content)
        except ValidationError as error:
            raise InvalidModelOutputError("reviewer output failed its strict schema") from error
        expected = {item.claim_id for item in request.candidates}
        actual = [item.claim_id for item in envelope.decisions]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise InvalidModelOutputError("reviewer decisions did not match the request claim IDs")
        decisions = tuple(
            AgentClaimDecision(
                claim_id=item.claim_id,
                decision=item.decision,
                suggested_predicate=(
                    item.suggested_predicate.value if item.suggested_predicate is not None else None
                ),
                priority=item.priority,
                reason_code=item.reason_code,
                rationale=item.rationale,
                risk_codes=tuple(sorted(set(item.risk_codes))),
            )
            for item in envelope.decisions
        )
        input_tokens = _count(response, "prompt_eval_count")
        output_tokens = _count(response, "eval_count")
        digest = sha256(
            f"{response.get('created_at', '')}\0{request.fingerprint_sha256}\0{content}".encode()
        ).hexdigest()[:32]
        return KnowledgeReviewResult(
            provider="ollama-local",
            model=self._model,
            response_id=f"ollama-review-{digest}",
            request_fingerprint_sha256=request.fingerprint_sha256,
            decisions=decisions,
            usage=ModelTokenUsage(input_tokens, output_tokens, input_tokens + output_tokens),
        )


def _count(response: Mapping[str, Any], key: str) -> int:
    value = response.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
