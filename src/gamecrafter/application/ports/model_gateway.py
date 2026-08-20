"""Provider-neutral boundary for evidence-bound candidate-claim extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from gamecrafter.domain.knowledge.claims import CandidateClaim

CLAIM_PROMPT_VERSION = "knowledge-claim-v2"
CLAIM_SCHEMA_VERSION = "knowledge-claim-v1"


class ModelGatewayError(RuntimeError):
    """Safe base error for model gateway failures."""


class ModelGatewayDisabledError(ModelGatewayError):
    """Raised when model execution is disabled by product policy."""


class ReplayFixtureNotFoundError(ModelGatewayError):
    """Raised when an offline request has no exact replay fixture."""


class InvalidModelOutputError(ModelGatewayError):
    """Raised when structured output or cited evidence is invalid."""


class ModelProviderError(ModelGatewayError):
    """Raised for a redacted provider-side failure."""


@dataclass(frozen=True, slots=True)
class ClaimExtractionRequest:
    """One bounded normalized-text chunk sent through a model boundary."""

    source_version_id: UUID
    subject_entity_key: str
    text: str
    text_start_offset: int
    locale: str
    region: str
    prompt_version: str
    schema_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_version_id, UUID):
            raise ValueError("source_version_id must be a UUID")
        for name in (
            "subject_entity_key",
            "text",
            "locale",
            "region",
            "prompt_version",
            "schema_version",
        ):
            value = getattr(self, name)
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.text_start_offset < 0:
            raise ValueError("text_start_offset must be nonnegative")

    @property
    def fingerprint_sha256(self) -> str:
        """Bind a replay to the exact source, chunk, prompt, and schema."""

        canonical = json.dumps(
            {
                "locale": self.locale,
                "prompt_version": self.prompt_version,
                "region": self.region,
                "schema_version": self.schema_version,
                "source_version_id": str(self.source_version_id),
                "subject_entity_key": self.subject_entity_key,
                "text": self.text,
                "text_start_offset": self.text_start_offset,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelTokenUsage:
    """Provider-reported usage retained without prompt or response bodies."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("token usage must contain integers")
        if min(values) < 0:
            raise ValueError("token usage must be nonnegative")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be smaller than input plus output")


@dataclass(frozen=True, slots=True)
class ClaimExtractionResult:
    """Validated candidate claims plus minimum model invocation metadata."""

    provider: str
    model: str
    response_id: str
    request_fingerprint_sha256: str
    claims: tuple[CandidateClaim, ...]
    usage: ModelTokenUsage

    def __post_init__(self) -> None:
        for name in ("provider", "model", "response_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")
        if len(self.request_fingerprint_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.request_fingerprint_sha256
        ):
            raise ValueError("request fingerprint must be a SHA-256 digest")


class ModelGateway(Protocol):
    """Extract reviewable candidate claims without exposing a model vendor."""

    def extract_claims(self, request: ClaimExtractionRequest) -> ClaimExtractionResult:
        """Return evidence-validated candidates or a safe gateway error."""
