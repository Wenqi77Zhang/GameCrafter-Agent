"""Strict structured-output schema and evidence-aware decoder."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
)

from gamecrafter.application.ports.model_gateway import (
    ClaimExtractionRequest,
    InvalidModelOutputError,
)
from gamecrafter.domain.knowledge.claims import (
    CandidateClaim,
    ClaimValueKind,
    EvidenceSpan,
    FactPredicate,
)


class StructuredEntityReference(BaseModel):
    """Only allowed JSON shape for an entity-reference claim."""

    model_config = ConfigDict(extra="forbid")

    entity_key: StrictStr = Field(min_length=1)


class StructuredEvidenceSpan(BaseModel):
    """Chunk-relative exact evidence returned by a model."""

    model_config = ConfigDict(extra="forbid")

    start_offset: StrictInt = Field(ge=0)
    end_offset: StrictInt = Field(gt=0)
    quote: StrictStr = Field(min_length=1)


class StructuredCandidateClaim(BaseModel):
    """Strict candidate shape before domain and source-text validation."""

    model_config = ConfigDict(extra="forbid")

    predicate: FactPredicate
    value_kind: ClaimValueKind
    value: (
        StrictStr
        | StrictInt
        | StrictFloat
        | StrictBool
        | StructuredEntityReference
        | list[StrictStr]
    )
    confidence: Annotated[float, Field(strict=True, ge=0, le=1)]
    evidence: list[StructuredEvidenceSpan] = Field(min_length=1)


class StructuredClaimEnvelope(BaseModel):
    """Top-level schema required from every model or replay fixture."""

    model_config = ConfigDict(extra="forbid")

    claims: list[StructuredCandidateClaim]


def strict_claim_schema() -> dict[str, Any]:
    """Return the provider-facing strict JSON Schema."""

    return StructuredClaimEnvelope.model_json_schema()


def decode_claim_output(
    payload: str | bytes | dict[str, Any],
    request: ClaimExtractionRequest,
) -> tuple[CandidateClaim, ...]:
    """Validate schema, value kinds, and exact source evidence."""

    try:
        if isinstance(payload, str | bytes):
            envelope = StructuredClaimEnvelope.model_validate_json(payload)
        else:
            envelope = StructuredClaimEnvelope.model_validate(payload)
    except ValidationError as error:
        raise InvalidModelOutputError("model output failed the strict claim schema") from error

    candidates: list[CandidateClaim] = []
    for raw_claim in envelope.claims:
        evidence: list[EvidenceSpan] = []
        for raw_span in raw_claim.evidence:
            if raw_span.end_offset > len(request.text):
                raise InvalidModelOutputError("evidence range exceeds the supplied text chunk")
            exact_quote = request.text[raw_span.start_offset : raw_span.end_offset]
            if exact_quote != raw_span.quote:
                raise InvalidModelOutputError("evidence quote does not match the supplied text")
            evidence.append(
                EvidenceSpan(
                    start_offset=request.text_start_offset + raw_span.start_offset,
                    end_offset=request.text_start_offset + raw_span.end_offset,
                    quote=raw_span.quote,
                )
            )

        value: Any = raw_claim.value
        if isinstance(value, StructuredEntityReference):
            value = value.model_dump()
        try:
            candidates.append(
                CandidateClaim(
                    predicate=raw_claim.predicate,
                    value_kind=raw_claim.value_kind,
                    value=value,
                    confidence=raw_claim.confidence,
                    evidence=tuple(evidence),
                )
            )
        except ValueError as error:
            raise InvalidModelOutputError("claim value does not match its declared kind") from error
    return tuple(candidates)
