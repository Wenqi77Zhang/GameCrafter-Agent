"""SQLAlchemy persistence for discovery candidates and immutable captures."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.ports.site_adapter import DiscoveredPage
from gamecrafter.application.ports.source_repository import (
    CaptureValidators,
    PersistedCapture,
    PreparedCapture,
    SelectedCandidate,
    SourceStateError,
)
from gamecrafter.domain.knowledge.sources import AssetRole, CandidateStatus, ChangeKind
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    DiscoveryCandidateRecord,
    IngestionRunRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
)


class SourcePersistenceError(SourceStateError):
    """Raised when a capture references missing or inconsistent durable state."""


class DatabaseSourceRepository:
    """Persist one run's candidates and evidence with idempotent identities."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        actor_id: str = "source-worker",
    ) -> None:
        self._session_factory = session_factory
        self._actor_id = actor_id

    def save_candidates(
        self,
        *,
        run_id: UUID,
        candidates: tuple[DiscoveredPage, ...],
    ) -> int:
        with self._session_factory.begin() as session:
            run = self._run(session, run_id)
            existing_urls = set(
                session.scalars(
                    select(DiscoveryCandidateRecord.canonical_url).where(
                        DiscoveryCandidateRecord.run_id == run_id
                    )
                )
            )
            added = 0
            for candidate in candidates:
                if candidate.canonical_url in existing_urls:
                    continue
                existing_urls.add(candidate.canonical_url)
                session.add(
                    DiscoveryCandidateRecord(
                        run_id=run.id,
                        project_id=run.project_id,
                        canonical_url=candidate.canonical_url,
                        site_key=candidate.site_key,
                        locale=candidate.locale,
                        region=candidate.region,
                        title=candidate.title,
                        published_at=candidate.published_at,
                        source_type=candidate.source_type.value,
                        raw_category=candidate.raw_category,
                        family_key=None,
                        classification_basis=candidate.classification_basis,
                        status=CandidateStatus.DISCOVERED.value,
                        details={"family_signal": candidate.family_signal},
                    )
                )
                added += 1
            session.add(
                self._event(
                    run=run,
                    event_type="source.candidates_discovered",
                    payload={"added": added, "received": len(candidates)},
                )
            )
            return added

    def capture_validators(
        self,
        *,
        run_id: UUID,
        canonical_url: str,
    ) -> CaptureValidators | None:
        with self._session_factory() as session:
            run = self._run(session, run_id)
            source = session.scalar(
                select(SourceRecord).where(
                    SourceRecord.project_id == run.project_id,
                    SourceRecord.canonical_url == canonical_url,
                )
            )
            if source is None:
                return None
            latest = self._latest_version(session, source.id)
            if latest is None:
                return None
            return CaptureValidators(
                etag=latest.http_etag,
                last_modified=latest.http_last_modified,
            )

    def selected_candidate(self, *, run_id: UUID, candidate_id: UUID) -> SelectedCandidate:
        with self._session_factory() as session:
            run = self._run(session, run_id)
            candidate = session.scalar(
                select(DiscoveryCandidateRecord).where(
                    DiscoveryCandidateRecord.id == candidate_id,
                    DiscoveryCandidateRecord.project_id == run.project_id,
                )
            )
            if candidate is None or candidate.status not in {
                CandidateStatus.SELECTED.value,
                CandidateStatus.IMPORTED.value,
            }:
                raise SourcePersistenceError(
                    "candidate must belong to this project and be selected before capture"
                )
            return SelectedCandidate(
                id=candidate.id,
                canonical_url=candidate.canonical_url,
                title=candidate.title,
                published_at=candidate.published_at,
            )

    def record_not_modified(
        self,
        *,
        run_id: UUID,
        canonical_url: str,
        candidate_id: UUID | None,
    ) -> PersistedCapture:
        with self._session_factory.begin() as session:
            run = self._run(session, run_id)
            source = session.scalar(
                select(SourceRecord)
                .where(
                    SourceRecord.project_id == run.project_id,
                    SourceRecord.canonical_url == canonical_url,
                )
                .with_for_update()
            )
            if source is None:
                raise SourcePersistenceError("304 response has no preceding source evidence")
            latest = self._latest_version(session, source.id)
            if latest is None:
                raise SourcePersistenceError("304 response has no preceding source version")
            self._link_candidate(
                session,
                project_id=run.project_id,
                candidate_id=candidate_id,
                source_id=source.id,
                canonical_url=canonical_url,
            )
            session.add(
                self._event(
                    run=run,
                    event_type="source.capture_not_modified",
                    payload={
                        "source_id": str(source.id),
                        "source_version_id": str(latest.id),
                        "version_number": latest.version_number,
                    },
                )
            )
            return PersistedCapture(
                source_id=source.id,
                source_version_id=latest.id,
                version_number=latest.version_number,
                created_version=False,
            )

    def persist_capture(
        self,
        *,
        run_id: UUID,
        candidate_id: UUID | None,
        capture: PreparedCapture,
    ) -> PersistedCapture:
        with self._session_factory.begin() as session:
            run = self._run(session, run_id)
            source = session.scalar(
                select(SourceRecord)
                .where(
                    SourceRecord.project_id == run.project_id,
                    SourceRecord.canonical_url == capture.source.canonical_url,
                )
                .with_for_update()
            )
            if source is None:
                source = SourceRecord(
                    project_id=run.project_id,
                    canonical_url=capture.source.canonical_url,
                    site_key=capture.source.site_key,
                    locale=capture.source.locale,
                    region=capture.source.region,
                    source_type=capture.source.source_type.value,
                    raw_category=capture.source.raw_category,
                )
                session.add(source)
                session.flush()

            duplicate = session.scalar(
                select(SourceVersionRecord).where(
                    SourceVersionRecord.source_id == source.id,
                    SourceVersionRecord.evidence_fingerprint_sha256
                    == capture.evidence_fingerprint_sha256,
                )
            )
            if duplicate is not None:
                self._link_candidate(
                    session,
                    project_id=run.project_id,
                    candidate_id=candidate_id,
                    source_id=source.id,
                    canonical_url=capture.source.canonical_url,
                )
                session.add(
                    self._event(
                        run=run,
                        event_type="source.capture_unchanged",
                        payload={
                            "source_id": str(source.id),
                            "source_version_id": str(duplicate.id),
                            "version_number": duplicate.version_number,
                            "fingerprint": capture.evidence_fingerprint_sha256,
                        },
                    )
                )
                return PersistedCapture(
                    source_id=source.id,
                    source_version_id=duplicate.id,
                    version_number=duplicate.version_number,
                    created_version=False,
                )

            previous = self._latest_version(session, source.id)
            raw_record = self._stored_object(session, capture.raw_object)
            normalized_record = self._stored_object(session, capture.normalized_object)
            version = SourceVersionRecord(
                source_id=source.id,
                previous_version_id=previous.id if previous is not None else None,
                version_number=previous.version_number + 1 if previous is not None else 1,
                title=capture.title,
                published_at=capture.published_at,
                fetched_at=capture.fetched_at,
                capture_method=capture.capture_method.value,
                change_kind=(
                    ChangeKind.MEANINGFUL.value
                    if previous is not None
                    else ChangeKind.INITIAL.value
                ),
                raw_content_sha256=capture.raw_object.digest.value,
                normalized_text_sha256=capture.normalized_object.digest.value,
                evidence_fingerprint_sha256=capture.evidence_fingerprint_sha256,
                parser_version=capture.parser_version,
                capture_policy_version=capture.capture_policy_version,
                http_etag=capture.etag,
                http_last_modified=capture.last_modified,
                details={
                    "classification_basis": capture.source.classification_basis,
                    "document_language": capture.document_language,
                    "family_signal": capture.source.family_signal,
                    "http_status": capture.http_status,
                    "image_candidate_count": capture.image_candidate_count,
                    "image_captured_count": len(capture.images),
                    "image_failure_count": capture.image_failure_count,
                },
            )
            session.add(version)
            session.flush()
            session.add_all(
                [
                    SourceAssetRecord(
                        source_version_id=version.id,
                        stored_object_id=raw_record.id,
                        role=AssetRole.RAW_HTML.value,
                        ordinal=0,
                        original_url=capture.source.canonical_url,
                    ),
                    SourceAssetRecord(
                        source_version_id=version.id,
                        stored_object_id=normalized_record.id,
                        role=AssetRole.NORMALIZED_TEXT.value,
                        ordinal=0,
                        original_url=capture.source.canonical_url,
                    ),
                ]
            )
            for ordinal, image in enumerate(capture.images):
                image_record = self._stored_object(session, image.stored_object)
                session.add(
                    SourceAssetRecord(
                        source_version_id=version.id,
                        stored_object_id=image_record.id,
                        role=AssetRole.IMAGE.value,
                        ordinal=ordinal,
                        original_url=image.original_url,
                        alt_text=image.alt_text,
                    )
                )
            self._link_candidate(
                session,
                project_id=run.project_id,
                candidate_id=candidate_id,
                source_id=source.id,
                canonical_url=capture.source.canonical_url,
            )
            session.add(
                self._event(
                    run=run,
                    event_type="source.version_captured",
                    payload={
                        "source_id": str(source.id),
                        "source_version_id": str(version.id),
                        "version_number": version.version_number,
                        "capture_method": capture.capture_method.value,
                        "raw_sha256": capture.raw_object.digest.value,
                        "normalized_sha256": capture.normalized_object.digest.value,
                        "fingerprint": capture.evidence_fingerprint_sha256,
                        "image_captured_count": len(capture.images),
                        "image_failure_count": capture.image_failure_count,
                    },
                )
            )
            return PersistedCapture(
                source_id=source.id,
                source_version_id=version.id,
                version_number=version.version_number,
                created_version=True,
            )

    @staticmethod
    def _run(session: Session, run_id: UUID) -> IngestionRunRecord:
        run = session.get(IngestionRunRecord, run_id)
        if run is None:
            raise SourcePersistenceError("source task references a missing ingestion run")
        return run

    @staticmethod
    def _latest_version(session: Session, source_id: UUID) -> SourceVersionRecord | None:
        return session.scalar(
            select(SourceVersionRecord)
            .where(SourceVersionRecord.source_id == source_id)
            .order_by(SourceVersionRecord.version_number.desc())
            .limit(1)
        )

    @staticmethod
    def _stored_object(session: Session, stored) -> StoredObjectRecord:
        record = session.scalar(
            select(StoredObjectRecord).where(StoredObjectRecord.sha256 == stored.digest.value)
        )
        if record is not None:
            if (
                record.object_key != stored.key
                or record.size_bytes != stored.size_bytes
                or record.media_type != stored.media_type
            ):
                raise SourcePersistenceError("stored-object metadata conflicts with its digest")
            return record
        record = StoredObjectRecord(
            object_key=stored.key,
            sha256=stored.digest.value,
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
            storage_backend="filesystem",
        )
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def _link_candidate(
        session: Session,
        *,
        project_id: UUID,
        candidate_id: UUID | None,
        source_id: UUID,
        canonical_url: str,
    ) -> None:
        if candidate_id is None:
            return
        candidate = session.scalar(
            select(DiscoveryCandidateRecord)
            .where(
                DiscoveryCandidateRecord.id == candidate_id,
                DiscoveryCandidateRecord.project_id == project_id,
            )
            .with_for_update()
        )
        if candidate is None or candidate.status not in {
            CandidateStatus.SELECTED.value,
            CandidateStatus.IMPORTED.value,
        }:
            raise SourcePersistenceError("candidate is not selected in this project")
        if candidate.canonical_url != canonical_url:
            raise SourcePersistenceError("captured source does not match selected candidate")
        candidate.status = CandidateStatus.IMPORTED.value
        candidate.imported_source_id = source_id

    def _event(
        self,
        *,
        run: IngestionRunRecord,
        event_type: str,
        payload: dict,
    ) -> AuditEventRecord:
        return AuditEventRecord(
            project_id=run.project_id,
            run_id=run.id,
            event_type=event_type,
            actor_type="worker",
            actor_id=self._actor_id,
            payload=payload,
        )
