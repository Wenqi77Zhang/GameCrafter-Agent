"""Private local text, transcript, and GDD evidence ingestion."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ProjectRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
    utc_now,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


class LocalSourceError(RuntimeError):
    """A safe validation or persistence error for local evidence."""


class DatabaseLocalSourceService:
    """Store local UTF-8 evidence without sending content outside the machine."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalObjectStorage,
        *,
        max_bytes: int,
    ) -> None:
        self._sessions = session_factory
        self._storage = storage
        self._max_bytes = max_bytes

    def import_text(
        self,
        *,
        project_id: UUID,
        document_key: str,
        kind: Literal["document", "transcript", "gdd"],
        title: str,
        filename: str,
        content: str,
        media_type: str,
        locale: str,
        region: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        clean_title = self._text(title, "title", 500)
        clean_filename = self._text(filename, "filename", 240)
        clean_locale = self._text(locale, "locale", 16)
        clean_region = self._text(region, "region", 32)
        clean_actor = self._text(actor_id, "actor", 120)
        clean_command = self._text(command_key, "idempotency key", 160)
        if kind not in {"document", "transcript", "gdd"}:
            raise LocalSourceError("unsupported local source kind")
        if media_type not in {
            "text/plain",
            "text/markdown",
            "text/vtt",
            "application/json",
        }:
            raise LocalSourceError("unsupported local source media type")
        if "\x00" in content:
            raise LocalSourceError("local source contains forbidden NUL characters")
        raw = content.encode("utf-8")
        normalized_text = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = normalized_text.encode("utf-8")
        if not normalized:
            raise LocalSourceError("local source content must not be blank")
        if len(raw) > self._max_bytes or len(normalized) > self._max_bytes:
            raise LocalSourceError("local source exceeded the configured private-document limit")
        payload_fingerprint = hashlib.sha256(
            b"\x00".join(
                (
                    kind.encode(),
                    document_key.encode(),
                    clean_title.encode(),
                    clean_filename.encode(),
                    media_type.encode(),
                    clean_locale.encode(),
                    clean_region.encode(),
                    raw,
                )
            )
        ).hexdigest()
        canonical_url = f"local://{project_id}/{document_key}"
        with self._sessions() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise LocalSourceError("project not found")
            existing_source = session.scalar(
                select(SourceRecord).where(
                    SourceRecord.project_id == project_id,
                    SourceRecord.canonical_url == canonical_url,
                )
            )
            existing_version = (
                session.scalar(
                    select(SourceVersionRecord)
                    .where(SourceVersionRecord.source_id == existing_source.id)
                    .order_by(SourceVersionRecord.version_number.desc())
                    .limit(1)
                )
                if existing_source is not None
                else None
            )
            if (
                existing_version is not None
                and existing_version.details.get("command_key") == clean_command
            ):
                if existing_version.details.get("command_fingerprint") != payload_fingerprint:
                    raise LocalSourceError(
                        "idempotency key was already used for different local content"
                    )
                source_id = existing_source.id
                version_id = existing_version.id
                return self.get_version(project_id, source_id, version_id), False
        raw_object = self._storage.put(
            BytesIO(raw), media_type=media_type, max_bytes=self._max_bytes
        )
        normalized_object = self._storage.put(
            BytesIO(normalized), media_type="text/plain; charset=utf-8", max_bytes=self._max_bytes
        )
        now = utc_now()
        with self._sessions.begin() as session:
            project = session.get(ProjectRecord, project_id)
            if project is None:
                raise LocalSourceError("project not found")
            source = session.scalar(
                select(SourceRecord)
                .where(
                    SourceRecord.project_id == project_id,
                    SourceRecord.canonical_url == canonical_url,
                )
                .with_for_update()
            )
            if source is None:
                source = SourceRecord(
                    project_id=project_id,
                    canonical_url=canonical_url,
                    site_key="local-private",
                    locale=clean_locale,
                    region=clean_region,
                    source_type=kind,
                    raw_category="user-owned-private-document",
                )
                session.add(source)
                session.flush()
            latest = session.scalar(
                select(SourceVersionRecord)
                .where(SourceVersionRecord.source_id == source.id)
                .order_by(SourceVersionRecord.version_number.desc())
                .limit(1)
            )
            if latest is not None and latest.details.get("command_key") == clean_command:
                if latest.details.get("command_fingerprint") != payload_fingerprint:
                    raise LocalSourceError(
                        "idempotency key was already used for different local content"
                    )
                version_id = latest.id
                created = False
            else:
                raw_record = self._stored_object(session, raw_object)
                normalized_record = self._stored_object(session, normalized_object)
                version = SourceVersionRecord(
                    source_id=source.id,
                    previous_version_id=latest.id if latest else None,
                    version_number=(latest.version_number + 1) if latest else 1,
                    title=clean_title,
                    fetched_at=now,
                    capture_method="local_upload",
                    change_kind="meaningful" if latest else "initial",
                    raw_content_sha256=raw_object.digest.value,
                    normalized_text_sha256=normalized_object.digest.value,
                    evidence_fingerprint_sha256=payload_fingerprint,
                    parser_version="local-unicode-text-v1",
                    capture_policy_version="private-local-source-v1",
                    details={
                        "private": True,
                        "filename": clean_filename,
                        "media_type": media_type,
                        "document_kind": kind,
                        "command_key": clean_command,
                        "command_fingerprint": payload_fingerprint,
                    },
                )
                session.add(version)
                session.flush()
                session.add_all(
                    [
                        SourceAssetRecord(
                            source_version_id=version.id,
                            stored_object_id=raw_record.id,
                            role="raw_document",
                            ordinal=0,
                            original_url=None,
                            details={"filename": clean_filename, "private": True},
                        ),
                        SourceAssetRecord(
                            source_version_id=version.id,
                            stored_object_id=normalized_record.id,
                            role="normalized_text",
                            ordinal=0,
                            original_url=None,
                            details={"private": True},
                        ),
                    ]
                )
                source.updated_at = now
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="source.local_version_imported",
                        actor_type="human",
                        actor_id=clean_actor,
                        payload={
                            "source_id": str(source.id),
                            "source_version_id": str(version.id),
                            "version_number": version.version_number,
                            "document_kind": kind,
                            "private": True,
                            "normalized_sha256": normalized_object.digest.value,
                        },
                    )
                )
                version_id = version.id
                created = True
            source_id = source.id
        return self.get_version(project_id, source_id, version_id), created

    def get_version(self, project_id: UUID, source_id: UUID, version_id: UUID) -> dict[str, object]:
        with self._sessions() as session:
            version = session.scalar(
                select(SourceVersionRecord)
                .join(SourceRecord, SourceRecord.id == SourceVersionRecord.source_id)
                .where(
                    SourceRecord.project_id == project_id,
                    SourceRecord.id == source_id,
                    SourceVersionRecord.id == version_id,
                )
            )
            if version is None:
                raise LocalSourceError("local source version not found")
            return {
                "source_id": str(source_id),
                "source_version_id": str(version.id),
                "version_number": version.version_number,
                "title": version.title,
                "capture_method": version.capture_method,
                "normalized_text_sha256": version.normalized_text_sha256,
                "private": bool(version.details.get("private")),
                "document_kind": version.details.get("document_kind"),
                "filename": version.details.get("filename"),
                "created_at": version.fetched_at.isoformat(),
            }

    @staticmethod
    def _stored_object(session: Session, stored) -> StoredObjectRecord:
        existing = session.scalar(
            select(StoredObjectRecord).where(StoredObjectRecord.sha256 == stored.digest.value)
        )
        if existing is not None:
            return existing
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
    def _text(value: str, label: str, maximum: int) -> str:
        clean = " ".join(value.split())
        if not clean or len(clean) > maximum:
            raise LocalSourceError(f"{label} must contain 1 to {maximum} characters")
        return clean
