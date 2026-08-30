"""Durable zero-cost knowledge-extraction job orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any
from uuid import UUID

from gamecrafter.application.jobs import ClaimedJob, TerminalJobError
from gamecrafter.application.knowledge_extraction import (
    ExtractionDocument,
    ExtractionHarness,
    ExtractionHarnessError,
)
from gamecrafter.application.ports.knowledge_repository import (
    ExtractionTarget,
    KnowledgeRepository,
    KnowledgeStateError,
)
from gamecrafter.application.ports.model_gateway import ModelGateway
from gamecrafter.application.ports.object_storage import ObjectIntegrityError, ObjectStorage
from gamecrafter.application.text_chunking import DeterministicTextChunker

EXTRACT_KNOWLEDGE_TASK = "knowledge.extract"


class KnowledgeExtractionHandlers:
    """Load verified source text, run the Harness, and atomically publish candidates."""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        object_storage: ObjectStorage,
        gateway: ModelGateway,
        document_max_bytes: int,
    ) -> None:
        if document_max_bytes <= 0:
            raise ValueError("document_max_bytes must be positive")
        self._repository = repository
        self._storage = object_storage
        self._gateway = gateway
        self._document_max_bytes = document_max_bytes

    def extract(self, job: ClaimedJob) -> None:
        """Execute one immutable source version and subject pair fail-closed."""

        try:
            source_version_id, subject_entity_id = _payload(job.payload)
            if self._repository.result_exists(job.run_id):
                return
            target = self._repository.target_for_run(
                run_id=job.run_id,
                source_version_id=source_version_id,
                subject_entity_id=subject_entity_id,
            )
            normalized_text = self._read_verified_text(target)
            observer = self._repository.observer(
                run_id=job.run_id,
                target=target,
                job_attempt=job.attempts,
            )
            result = ExtractionHarness(
                gateway=self._gateway,
                chunker=DeterministicTextChunker(),
                observer=observer,
            ).run(
                ExtractionDocument(
                    source_version_id=target.source_version_id,
                    subject_entity_key=target.subject_entity_key,
                    subject_labels=target.subject_labels,
                    normalized_text=normalized_text,
                    locale=target.locale,
                    region=target.region,
                )
            )
            self._repository.persist_result(
                run_id=job.run_id,
                target=target,
                job_attempt=job.attempts,
                normalized_text=normalized_text,
                result=result,
            )
        except (ExtractionHarnessError, KnowledgeStateError, ObjectIntegrityError) as error:
            detail = (
                str(error) if isinstance(error, ExtractionHarnessError) else type(error).__name__
            )
            raise TerminalJobError(f"knowledge extraction stopped ({detail})") from None
        except (FileNotFoundError, UnicodeDecodeError, ValueError) as error:
            raise TerminalJobError(
                f"knowledge extraction input is invalid ({type(error).__name__})"
            ) from None

    def _read_verified_text(self, target: ExtractionTarget) -> str:
        if target.size_bytes > self._document_max_bytes:
            raise KnowledgeStateError("normalized source text exceeds the extraction byte limit")
        with self._storage.open(target.object_key) as stored:
            body = stored.read(self._document_max_bytes + 1)
        if len(body) > self._document_max_bytes or len(body) != target.size_bytes:
            raise ObjectIntegrityError("normalized source text size does not match metadata")
        if sha256(body).hexdigest() != target.object_sha256:
            raise ObjectIntegrityError("normalized source text digest does not match metadata")
        text = body.decode("utf-8")
        if not text.strip():
            raise KnowledgeStateError("normalized source text is blank")
        return text


def _payload(payload: Mapping[str, Any]) -> tuple[UUID, UUID]:
    if set(payload) != {"source_version_id", "subject_entity_id"}:
        raise ValueError("knowledge extraction payload has unsupported fields")
    try:
        source_version_id = UUID(str(payload["source_version_id"]))
        subject_entity_id = UUID(str(payload["subject_entity_id"]))
    except (TypeError, ValueError) as error:
        raise ValueError("knowledge extraction payload IDs must be UUIDs") from error
    return source_version_id, subject_entity_id
