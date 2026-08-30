"""Deterministic orchestration for evidence-bound candidate extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

from gamecrafter.application.ports.model_gateway import (
    CLAIM_PROMPT_VERSION,
    CLAIM_SCHEMA_VERSION,
    ClaimExtractionRequest,
    InvalidModelOutputError,
    ModelGateway,
    ModelTokenUsage,
)
from gamecrafter.application.text_chunking import (
    CHUNKER_VERSION,
    DeterministicTextChunker,
    TextChunk,
)
from gamecrafter.domain.knowledge.claims import CandidateClaim


class ExtractionHarnessError(RuntimeError):
    """Safe whole-document failure without source text or provider details."""


@dataclass(frozen=True, slots=True)
class ExtractionDocument:
    """Immutable normalized source text and minimum extraction context."""

    source_version_id: UUID
    subject_entity_key: str
    subject_labels: tuple[str, ...]
    normalized_text: str
    locale: str
    region: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_version_id, UUID):
            raise ValueError("source_version_id must be a UUID")
        for name in ("subject_entity_key", "normalized_text", "locale", "region"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        if not self.subject_labels or any(
            not isinstance(label, str) or not label.strip() for label in self.subject_labels
        ):
            raise ValueError("subject_labels must contain non-blank strings")

    @property
    def text_sha256(self) -> str:
        return sha256(self.normalized_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChunkInvocation:
    """Safe replayable trace for one successful chunk invocation."""

    chunk_index: int
    chunk_id: str
    start_offset: int
    end_offset: int
    request_fingerprint_sha256: str
    provider: str
    model: str
    response_id: str
    usage: ModelTokenUsage
    claim_count: int


@dataclass(frozen=True, slots=True)
class ExtractionRunResult:
    """Validated document-level output and deterministic invocation manifest."""

    source_version_id: UUID
    document_sha256: str
    chunker_version: str
    max_chars: int
    overlap_chars: int
    prompt_version: str
    schema_version: str
    invocations: tuple[ChunkInvocation, ...]
    claims: tuple[CandidateClaim, ...]
    usage: ModelTokenUsage


class ExtractionObserver(Protocol):
    """Persist safe per-chunk lifecycle metadata outside the pure Harness."""

    def started(self, *, chunk: TextChunk, request: ClaimExtractionRequest) -> None:
        """Record a request before the gateway can perform work."""

    def succeeded(self, invocation: ChunkInvocation) -> None:
        """Record a validated invocation without prompt or response bodies."""

    def failed(
        self,
        *,
        chunk: TextChunk,
        request_fingerprint_sha256: str,
        error_code: str,
    ) -> None:
        """Record one redacted failure classification."""


class NullExtractionObserver:
    """Default no-op observer preserving the C2.2 pure in-memory behavior."""

    def started(self, *, chunk: TextChunk, request: ClaimExtractionRequest) -> None:
        del chunk, request

    def succeeded(self, invocation: ChunkInvocation) -> None:
        del invocation

    def failed(
        self,
        *,
        chunk: TextChunk,
        request_fingerprint_sha256: str,
        error_code: str,
    ) -> None:
        del chunk, request_fingerprint_sha256, error_code


class ExtractionHarness:
    """Run one specialist extractor over stable chunks, failing closed on any error."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        chunker: DeterministicTextChunker,
        observer: ExtractionObserver | None = None,
        prompt_version: str = CLAIM_PROMPT_VERSION,
        schema_version: str = CLAIM_SCHEMA_VERSION,
    ) -> None:
        if not prompt_version.strip() or not schema_version.strip():
            raise ValueError("prompt and schema versions must not be blank")
        self._gateway = gateway
        self._chunker = chunker
        self._observer = observer or NullExtractionObserver()
        self._prompt_version = prompt_version
        self._schema_version = schema_version

    def run(self, document: ExtractionDocument) -> ExtractionRunResult:
        """Extract in stable order; never publish a partial document result."""

        chunks = self._chunker.split(document.normalized_text)
        invocations: list[ChunkInvocation] = []
        claims: list[CandidateClaim] = []
        input_tokens = output_tokens = total_tokens = 0

        for chunk in chunks:
            request = self._request(document, chunk)
            self._observer.started(chunk=chunk, request=request)
            try:
                result = self._gateway.extract_claims(request)
            except Exception as error:
                self._observer.failed(
                    chunk=chunk,
                    request_fingerprint_sha256=request.fingerprint_sha256,
                    error_code=type(error).__name__,
                )
                safe_detail = f": {error}" if isinstance(error, InvalidModelOutputError) else ""
                raise ExtractionHarnessError(
                    f"claim extraction failed for chunk {chunk.index} "
                    f"({type(error).__name__}{safe_detail})"
                ) from None
            if result.request_fingerprint_sha256 != request.fingerprint_sha256:
                self._observer.failed(
                    chunk=chunk,
                    request_fingerprint_sha256=request.fingerprint_sha256,
                    error_code="RequestFingerprintMismatch",
                )
                raise ExtractionHarnessError(
                    f"claim extraction returned a mismatched fingerprint for chunk {chunk.index}"
                )
            claims.extend(result.claims)
            input_tokens += result.usage.input_tokens
            output_tokens += result.usage.output_tokens
            total_tokens += result.usage.total_tokens
            invocation = ChunkInvocation(
                chunk_index=chunk.index,
                chunk_id=chunk.chunk_id,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                request_fingerprint_sha256=request.fingerprint_sha256,
                provider=result.provider,
                model=result.model,
                response_id=result.response_id,
                usage=result.usage,
                claim_count=len(result.claims),
            )
            self._observer.succeeded(invocation)
            invocations.append(invocation)

        return ExtractionRunResult(
            source_version_id=document.source_version_id,
            document_sha256=document.text_sha256,
            chunker_version=CHUNKER_VERSION,
            max_chars=self._chunker.max_chars,
            overlap_chars=self._chunker.overlap_chars,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
            invocations=tuple(invocations),
            claims=_deduplicate_claims(claims),
            usage=ModelTokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
        )

    def _request(self, document: ExtractionDocument, chunk: TextChunk) -> ClaimExtractionRequest:
        return ClaimExtractionRequest(
            source_version_id=document.source_version_id,
            subject_entity_key=document.subject_entity_key,
            subject_labels=document.subject_labels,
            text=chunk.text,
            text_start_offset=chunk.start_offset,
            locale=document.locale,
            region=document.region,
            prompt_version=self._prompt_version,
            schema_version=self._schema_version,
        )


def _deduplicate_claims(claims: list[CandidateClaim]) -> tuple[CandidateClaim, ...]:
    unique: list[CandidateClaim] = []
    seen: set[str] = set()
    for claim in claims:
        key = json.dumps(
            {
                "evidence": [
                    {
                        "end": span.end_offset,
                        "quote": span.quote,
                        "start": span.start_offset,
                    }
                    for span in claim.evidence
                ],
                "predicate": claim.predicate.value,
                "value": _json_value(claim.value),
                "value_kind": claim.value_kind.value,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if key not in seen:
            seen.add(key)
            unique.append(claim)
    return tuple(unique)


def _json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    return value
