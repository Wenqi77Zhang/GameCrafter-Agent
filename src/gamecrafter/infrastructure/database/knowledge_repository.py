"""SQLAlchemy persistence for durable extraction traces and candidate claims."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.knowledge_extraction import (
    ChunkInvocation,
    ExtractionObserver,
    ExtractionRunResult,
)
from gamecrafter.application.ports.knowledge_repository import (
    ExtractionTarget,
    KnowledgeStateError,
)
from gamecrafter.application.ports.model_gateway import ClaimExtractionRequest
from gamecrafter.application.text_chunking import TextChunk
from gamecrafter.domain.knowledge.claims import (
    CandidateClaim,
    normalize_claim_value,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRecord,
    KnowledgeEntityRevisionRecord,
    KnowledgeExtractionResultRecord,
    ModelInvocationRecord,
    ProjectRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
    WorkflowRunRecord,
)

_NORMALIZED_TEXT_ROLE = "normalized_text"
_EXTRACTION_KIND = "knowledge.extract"


class DatabaseExtractionObserver(ExtractionObserver):
    """Persist one safe lifecycle row per chunk and durable job attempt."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        run_id: UUID,
        target: ExtractionTarget,
        job_attempt: int,
    ) -> None:
        self._session_factory = session_factory
        self._run_id = run_id
        self._target = target
        self._job_attempt = job_attempt

    def started(self, *, chunk: TextChunk, request: ClaimExtractionRequest) -> None:
        if request.source_version_id != self._target.source_version_id:
            raise KnowledgeStateError("invocation source version changed after preflight")
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            record = self._record(session, chunk.index)
            if record is None:
                session.add(
                    ModelInvocationRecord(
                        project_id=self._target.project_id,
                        run_id=self._run_id,
                        source_version_id=self._target.source_version_id,
                        subject_entity_id=self._target.subject_entity_id,
                        job_attempt=self._job_attempt,
                        chunk_index=chunk.index,
                        chunk_id=chunk.chunk_id,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        request_fingerprint_sha256=request.fingerprint_sha256,
                        status="running",
                        started_at=now,
                    )
                )
                return
            self._require_identity(record, chunk, request.fingerprint_sha256)
            if record.status == "succeeded":
                return
            record.status = "running"
            record.provider = None
            record.model = None
            record.response_id = None
            record.input_tokens = 0
            record.output_tokens = 0
            record.total_tokens = 0
            record.claim_count = 0
            record.error_code = None
            record.started_at = now
            record.finished_at = None

    def succeeded(self, invocation: ChunkInvocation) -> None:
        with self._session_factory.begin() as session:
            record = self._required_record(session, invocation.chunk_index)
            self._require_invocation_identity(record, invocation)
            record.status = "succeeded"
            record.provider = invocation.provider
            record.model = invocation.model
            record.response_id = invocation.response_id
            record.input_tokens = invocation.usage.input_tokens
            record.output_tokens = invocation.usage.output_tokens
            record.total_tokens = invocation.usage.total_tokens
            record.claim_count = invocation.claim_count
            record.error_code = None
            record.finished_at = datetime.now(UTC)

    def failed(
        self,
        *,
        chunk: TextChunk,
        request_fingerprint_sha256: str,
        error_code: str,
    ) -> None:
        with self._session_factory.begin() as session:
            record = self._required_record(session, chunk.index)
            self._require_identity(record, chunk, request_fingerprint_sha256)
            record.status = "failed"
            record.error_code = error_code[:80]
            record.finished_at = datetime.now(UTC)

    def _record(self, session: Session, chunk_index: int) -> ModelInvocationRecord | None:
        return session.scalar(
            select(ModelInvocationRecord).where(
                ModelInvocationRecord.run_id == self._run_id,
                ModelInvocationRecord.job_attempt == self._job_attempt,
                ModelInvocationRecord.chunk_index == chunk_index,
            )
        )

    def _required_record(self, session: Session, chunk_index: int) -> ModelInvocationRecord:
        record = self._record(session, chunk_index)
        if record is None:
            raise KnowledgeStateError("model invocation lifecycle started without a durable row")
        return record

    @staticmethod
    def _require_identity(
        record: ModelInvocationRecord,
        chunk: TextChunk,
        request_fingerprint_sha256: str,
    ) -> None:
        if (
            record.chunk_id != chunk.chunk_id
            or record.start_offset != chunk.start_offset
            or record.end_offset != chunk.end_offset
            or record.request_fingerprint_sha256 != request_fingerprint_sha256
        ):
            raise KnowledgeStateError("model invocation identity changed during retry")

    @staticmethod
    def _require_invocation_identity(
        record: ModelInvocationRecord,
        invocation: ChunkInvocation,
    ) -> None:
        if (
            record.chunk_id != invocation.chunk_id
            or record.start_offset != invocation.start_offset
            or record.end_offset != invocation.end_offset
            or record.request_fingerprint_sha256 != invocation.request_fingerprint_sha256
        ):
            raise KnowledgeStateError("model invocation result does not match its durable request")


class DatabaseKnowledgeRepository:
    """Preserve extraction idempotency, evidence lineage, and redacted traces."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        actor_id: str = "knowledge-worker",
    ) -> None:
        self._session_factory = session_factory
        self._actor_id = actor_id

    def validate_target(
        self,
        *,
        project_id: UUID,
        source_version_id: UUID,
        subject_entity_id: UUID,
    ) -> ExtractionTarget:
        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise KnowledgeStateError("project not found")
            return self._target(
                session,
                project_id=project_id,
                source_version_id=source_version_id,
                subject_entity_id=subject_entity_id,
            )

    def target_for_run(
        self,
        *,
        run_id: UUID,
        source_version_id: UUID,
        subject_entity_id: UUID,
    ) -> ExtractionTarget:
        with self._session_factory() as session:
            run = session.get(WorkflowRunRecord, run_id)
            if run is None or run.workflow_kind != _EXTRACTION_KIND:
                raise KnowledgeStateError(
                    "knowledge extraction run is missing or has the wrong kind"
                )
            return self._target(
                session,
                project_id=run.project_id,
                source_version_id=source_version_id,
                subject_entity_id=subject_entity_id,
            )

    def result_exists(self, run_id: UUID) -> bool:
        with self._session_factory() as session:
            return session.get(KnowledgeExtractionResultRecord, run_id) is not None

    def observer(
        self,
        *,
        run_id: UUID,
        target: ExtractionTarget,
        job_attempt: int,
    ) -> ExtractionObserver:
        return DatabaseExtractionObserver(
            self._session_factory,
            run_id=run_id,
            target=target,
            job_attempt=job_attempt,
        )

    def persist_result(
        self,
        *,
        run_id: UUID,
        target: ExtractionTarget,
        job_attempt: int,
        normalized_text: str,
        result: ExtractionRunResult,
    ) -> int:
        if result.source_version_id != target.source_version_id:
            raise KnowledgeStateError("extraction result source version does not match target")
        if sha256(normalized_text.encode("utf-8")).hexdigest() != result.document_sha256:
            raise KnowledgeStateError("extraction result document digest does not match input")
        with self._session_factory.begin() as session:
            existing = session.get(KnowledgeExtractionResultRecord, run_id)
            if existing is not None:
                return existing.claim_count
            run = session.get(WorkflowRunRecord, run_id, with_for_update=True)
            if run is None or run.project_id != target.project_id:
                raise KnowledgeStateError("extraction result run does not match its project")
            durable_target = self._target(
                session,
                project_id=run.project_id,
                source_version_id=target.source_version_id,
                subject_entity_id=target.subject_entity_id,
            )
            if durable_target != target:
                raise KnowledgeStateError("extraction target metadata changed before persistence")

            invocations = list(
                session.scalars(
                    select(ModelInvocationRecord)
                    .where(
                        ModelInvocationRecord.run_id == run_id,
                        ModelInvocationRecord.job_attempt == job_attempt,
                    )
                    .order_by(ModelInvocationRecord.chunk_index)
                )
            )
            self._validate_invocations(invocations, result)
            providers = {(item.provider, item.model) for item in result.invocations}
            if len(providers) != 1:
                raise KnowledgeStateError("one extraction result must use one provider and model")
            provider, model = next(iter(providers))

            for claim in result.claims:
                self._persist_claim(
                    session,
                    run=run,
                    target=target,
                    normalized_text=normalized_text,
                    provider=provider,
                    model=model,
                    prompt_version=result.prompt_version,
                    schema_version=result.schema_version,
                    claim=claim,
                )
            session.add(
                KnowledgeExtractionResultRecord(
                    run_id=run.id,
                    project_id=run.project_id,
                    source_version_id=target.source_version_id,
                    subject_entity_id=target.subject_entity_id,
                    document_sha256=result.document_sha256,
                    manifest_sha256=_manifest_sha256(result),
                    chunker_version=result.chunker_version,
                    max_chars=result.max_chars,
                    overlap_chars=result.overlap_chars,
                    prompt_version=result.prompt_version,
                    schema_version=result.schema_version,
                    invocation_count=len(result.invocations),
                    claim_count=len(result.claims),
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    total_tokens=result.usage.total_tokens,
                )
            )
            session.add(
                AuditEventRecord(
                    project_id=run.project_id,
                    run_id=run.id,
                    event_type="knowledge.extraction_persisted",
                    actor_type="worker",
                    actor_id=self._actor_id,
                    payload={
                        "source_version_id": str(target.source_version_id),
                        "subject_entity_id": str(target.subject_entity_id),
                        "invocation_count": len(result.invocations),
                        "claim_count": len(result.claims),
                        "total_tokens": result.usage.total_tokens,
                        "manifest_sha256": _manifest_sha256(result),
                    },
                )
            )
            return len(result.claims)

    def extraction_result(self, *, project_id: UUID, run_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            result = session.scalar(
                select(KnowledgeExtractionResultRecord).where(
                    KnowledgeExtractionResultRecord.run_id == run_id,
                    KnowledgeExtractionResultRecord.project_id == project_id,
                )
            )
            if result is None:
                raise KnowledgeStateError("knowledge extraction result not found")
            invocations = list(
                session.scalars(
                    select(ModelInvocationRecord)
                    .where(ModelInvocationRecord.run_id == run_id)
                    .order_by(ModelInvocationRecord.job_attempt, ModelInvocationRecord.chunk_index)
                )
            )
            return {
                "run_id": str(result.run_id),
                "project_id": str(result.project_id),
                "source_version_id": str(result.source_version_id),
                "subject_entity_id": str(result.subject_entity_id),
                "document_sha256": result.document_sha256,
                "manifest_sha256": result.manifest_sha256,
                "chunker_version": result.chunker_version,
                "prompt_version": result.prompt_version,
                "schema_version": result.schema_version,
                "invocation_count": result.invocation_count,
                "claim_count": result.claim_count,
                "usage": {
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "total_tokens": result.total_tokens,
                },
                "created_at": result.created_at.isoformat(),
                "invocations": [self._invocation(item) for item in invocations],
            }

    def list_claims(
        self,
        project_id: UUID,
        *,
        subject_entity_id: UUID | None = None,
        extraction_run_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise KnowledgeStateError("project not found")
            statement = select(KnowledgeClaimRecord).where(
                KnowledgeClaimRecord.project_id == project_id
            )
            if subject_entity_id is not None:
                statement = statement.where(
                    KnowledgeClaimRecord.subject_entity_id == subject_entity_id
                )
            if extraction_run_id is not None:
                statement = statement.where(
                    KnowledgeClaimRecord.extraction_run_id == extraction_run_id
                )
            claims = list(
                session.scalars(
                    statement.order_by(KnowledgeClaimRecord.created_at, KnowledgeClaimRecord.id)
                )
            )
            items: list[dict[str, object]] = []
            for claim in claims:
                spans = list(
                    session.scalars(
                        select(ClaimEvidenceSpanRecord)
                        .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
                        .order_by(ClaimEvidenceSpanRecord.ordinal)
                    )
                )
                reviews = list(
                    session.scalars(
                        select(ClaimReviewRecord)
                        .where(ClaimReviewRecord.claim_id == claim.id)
                        .order_by(ClaimReviewRecord.created_at, ClaimReviewRecord.id)
                    )
                )
                delivered_reviews = [self._review(review) for review in reviews]
                latest_review = delivered_reviews[-1] if delivered_reviews else None
                items.append(
                    {
                        "id": str(claim.id),
                        "project_id": str(claim.project_id),
                        "subject_entity_id": str(claim.subject_entity_id),
                        "extraction_run_id": (
                            str(claim.extraction_run_id)
                            if claim.extraction_run_id is not None
                            else None
                        ),
                        "predicate": claim.predicate,
                        "value_kind": claim.value_kind,
                        "value": claim.value,
                        "normalized_value": claim.normalized_value,
                        "confidence": float(claim.confidence),
                        "locale": claim.locale,
                        "region": claim.region,
                        "model_provider": claim.model_provider,
                        "model_name": claim.model_name,
                        "prompt_version": claim.prompt_version,
                        "schema_version": claim.schema_version,
                        "status": _claim_status(latest_review),
                        "created_at": claim.created_at.isoformat(),
                        "evidence": [self._evidence(session, span) for span in spans],
                        "reviews": delivered_reviews,
                        "latest_review": latest_review,
                    }
                )
            return items

    @staticmethod
    def _review(review: ClaimReviewRecord) -> dict[str, object]:
        return {
            "id": str(review.id),
            "decision": review.decision,
            "approved_value_kind": review.approved_value_kind,
            "approved_value": review.approved_value,
            "approved_normalized_value": review.approved_normalized_value,
            "reason": review.reason,
            "reviewer_id": review.reviewer_id,
            "created_at": review.created_at.isoformat(),
        }

    @staticmethod
    def _evidence(
        session: Session,
        span: ClaimEvidenceSpanRecord,
    ) -> dict[str, object]:
        version = session.get(SourceVersionRecord, span.source_version_id)
        if version is None:
            raise KnowledgeStateError("claim evidence source version not found")
        source = session.get(SourceRecord, version.source_id)
        if source is None:
            raise KnowledgeStateError("claim evidence source not found")
        return {
            "source_version_id": str(span.source_version_id),
            "source_id": str(source.id),
            "source_url": source.canonical_url,
            "source_title": version.title,
            "source_version_number": version.version_number,
            "locale": source.locale,
            "region": source.region,
            "fetched_at": version.fetched_at.isoformat(),
            "ordinal": span.ordinal,
            "start_offset": span.start_offset,
            "end_offset": span.end_offset,
            "quote": span.quote,
            "quote_sha256": span.quote_sha256,
        }

    @staticmethod
    def _target(
        session: Session,
        *,
        project_id: UUID,
        source_version_id: UUID,
        subject_entity_id: UUID,
    ) -> ExtractionTarget:
        entity = session.get(KnowledgeEntityRecord, subject_entity_id)
        if entity is None or entity.project_id != project_id:
            raise KnowledgeStateError("subject entity must belong to the extraction project")
        latest_entity_revision = session.scalar(
            select(KnowledgeEntityRevisionRecord)
            .where(KnowledgeEntityRevisionRecord.entity_id == entity.id)
            .order_by(KnowledgeEntityRevisionRecord.revision_number.desc())
            .limit(1)
        )
        if latest_entity_revision is not None and latest_entity_revision.status == "archived":
            raise KnowledgeStateError("archived subject entity cannot be extracted")
        version = session.get(SourceVersionRecord, source_version_id)
        if version is None:
            raise KnowledgeStateError("source version not found")
        source = session.get(SourceRecord, version.source_id)
        if source is None or source.project_id != project_id:
            raise KnowledgeStateError("source version must belong to the extraction project")
        row = session.execute(
            select(SourceAssetRecord, StoredObjectRecord)
            .join(
                StoredObjectRecord,
                StoredObjectRecord.id == SourceAssetRecord.stored_object_id,
            )
            .where(
                SourceAssetRecord.source_version_id == source_version_id,
                SourceAssetRecord.role == _NORMALIZED_TEXT_ROLE,
                SourceAssetRecord.ordinal == 0,
            )
        ).one_or_none()
        if row is None:
            raise KnowledgeStateError("source version has no normalized-text evidence object")
        asset, stored = row
        del asset
        if stored.storage_backend != "filesystem":
            raise KnowledgeStateError("normalized source text uses an unsupported storage backend")
        if not stored.media_type.lower().startswith("text/plain"):
            raise KnowledgeStateError("normalized source object is not plain text")
        if stored.sha256 != version.normalized_text_sha256:
            raise KnowledgeStateError(
                "normalized source digest conflicts with source-version metadata"
            )
        return ExtractionTarget(
            project_id=project_id,
            source_version_id=version.id,
            subject_entity_id=entity.id,
            subject_entity_key=entity.canonical_key,
            locale=source.locale,
            region=source.region,
            object_key=stored.object_key,
            object_sha256=stored.sha256,
            size_bytes=stored.size_bytes,
        )

    @staticmethod
    def _validate_invocations(
        records: list[ModelInvocationRecord],
        result: ExtractionRunResult,
    ) -> None:
        if len(records) != len(result.invocations):
            raise KnowledgeStateError("durable invocation count does not match extraction result")
        for record, invocation in zip(records, result.invocations, strict=True):
            if (
                record.status != "succeeded"
                or record.chunk_index != invocation.chunk_index
                or record.chunk_id != invocation.chunk_id
                or record.start_offset != invocation.start_offset
                or record.end_offset != invocation.end_offset
                or record.request_fingerprint_sha256 != invocation.request_fingerprint_sha256
                or record.provider != invocation.provider
                or record.model != invocation.model
                or record.response_id != invocation.response_id
                or record.input_tokens != invocation.usage.input_tokens
                or record.output_tokens != invocation.usage.output_tokens
                or record.total_tokens != invocation.usage.total_tokens
                or record.claim_count != invocation.claim_count
            ):
                raise KnowledgeStateError("durable invocation does not match extraction manifest")

    @staticmethod
    def _persist_claim(
        session: Session,
        *,
        run: WorkflowRunRecord,
        target: ExtractionTarget,
        normalized_text: str,
        provider: str | None,
        model: str | None,
        prompt_version: str,
        schema_version: str,
        claim: CandidateClaim,
    ) -> None:
        if provider is None or model is None:
            raise KnowledgeStateError("successful extraction is missing provider metadata")
        value_json = _json_value(claim.value)
        normalized_value = normalize_claim_value(claim.value_kind, value_json)
        value_fingerprint = sha256(
            _canonical_json({"kind": claim.value_kind.value, "value": value_json}).encode("utf-8")
        ).hexdigest()
        scope_fingerprint = sha256(
            _canonical_json(
                {
                    "effective_from": None,
                    "effective_to": None,
                    "game_version": None,
                    "locale": target.locale,
                    "region": target.region,
                }
            ).encode("utf-8")
        ).hexdigest()
        record = KnowledgeClaimRecord(
            project_id=run.project_id,
            subject_entity_id=target.subject_entity_id,
            extraction_run_id=run.id,
            predicate=claim.predicate.value,
            value_kind=claim.value_kind.value,
            value=value_json,
            normalized_value=normalized_value,
            value_fingerprint_sha256=value_fingerprint,
            scope_fingerprint_sha256=scope_fingerprint,
            confidence=claim.confidence,
            locale=target.locale,
            region=target.region,
            model_provider=provider,
            model_name=model,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )
        session.add(record)
        session.flush()
        for ordinal, span in enumerate(claim.evidence):
            if normalized_text[span.start_offset : span.end_offset] != span.quote:
                raise KnowledgeStateError("claim evidence no longer matches normalized source text")
            session.add(
                ClaimEvidenceSpanRecord(
                    claim_id=record.id,
                    source_version_id=target.source_version_id,
                    ordinal=ordinal,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    quote=span.quote,
                    quote_sha256=span.quote_sha256,
                )
            )

    @staticmethod
    def _invocation(record: ModelInvocationRecord) -> dict[str, object]:
        return {
            "id": str(record.id),
            "job_attempt": record.job_attempt,
            "chunk_index": record.chunk_index,
            "chunk_id": record.chunk_id,
            "start_offset": record.start_offset,
            "end_offset": record.end_offset,
            "request_fingerprint_sha256": record.request_fingerprint_sha256,
            "status": record.status,
            "provider": record.provider,
            "model": record.model,
            "response_id": record.response_id,
            "usage": {
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
            },
            "claim_count": record.claim_count,
            "error_code": record.error_code,
            "started_at": record.started_at.isoformat(),
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        }


def _json_value(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _claim_status(latest_review: dict[str, object] | None) -> str:
    if latest_review is None:
        return "candidate_unreviewed"
    return {
        "approve": "human_approved",
        "approve_with_edit": "human_approved_with_edit",
        "reject": "human_rejected",
        "defer": "human_deferred",
    }[str(latest_review["decision"])]


def _manifest_sha256(result: ExtractionRunResult) -> str:
    return sha256(
        _canonical_json(
            {
                "chunker_version": result.chunker_version,
                "document_sha256": result.document_sha256,
                "invocations": [
                    {
                        "chunk_id": item.chunk_id,
                        "chunk_index": item.chunk_index,
                        "claim_count": item.claim_count,
                        "end_offset": item.end_offset,
                        "model": item.model,
                        "provider": item.provider,
                        "request_fingerprint_sha256": item.request_fingerprint_sha256,
                        "response_id": item.response_id,
                        "start_offset": item.start_offset,
                        "usage": {
                            "input_tokens": item.usage.input_tokens,
                            "output_tokens": item.usage.output_tokens,
                            "total_tokens": item.usage.total_tokens,
                        },
                    }
                    for item in result.invocations
                ],
                "max_chars": result.max_chars,
                "overlap_chars": result.overlap_chars,
                "prompt_version": result.prompt_version,
                "schema_version": result.schema_version,
            }
        ).encode("utf-8")
    ).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
