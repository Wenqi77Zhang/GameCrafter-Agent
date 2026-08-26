"""Deterministic, evidence-bound GDD structure and assumption workflow."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    GddAssumptionRecord,
    GddChapterRecord,
    GddDocumentRecord,
    GddRevisionRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
    utc_now,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

_HEADING = re.compile(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*$")
_PARSER_VERSION = "markdown-heading-offsets-v1"


class GddError(RuntimeError):
    """Safe GDD validation or state-transition error."""


class DatabaseGddService:
    """Keep sourced chapters, human assumptions, and approvals distinct and append-only."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalObjectStorage,
    ) -> None:
        self._sessions = session_factory
        self._storage = storage

    def create_document(
        self,
        *,
        project_id: UUID,
        source_version_id: UUID,
        actor_id: str,
    ) -> tuple[dict[str, object], bool]:
        actor = self._clean(actor_id, "actor", 120)
        with self._sessions.begin() as session:
            source_version = session.scalar(
                select(SourceVersionRecord)
                .join(SourceRecord, SourceRecord.id == SourceVersionRecord.source_id)
                .where(
                    SourceRecord.project_id == project_id,
                    SourceRecord.source_type == "gdd",
                    SourceVersionRecord.id == source_version_id,
                    SourceVersionRecord.capture_method == "local_upload",
                )
            )
            if source_version is None:
                raise GddError("private GDD source version not found")
            existing = session.scalar(
                select(GddDocumentRecord).where(
                    GddDocumentRecord.project_id == project_id,
                    GddDocumentRecord.source_version_id == source_version_id,
                )
            )
            if existing is not None:
                document_id = existing.id
                created = False
            else:
                text = self._load_text(session, source_version)
                chapters = self._parse(text)
                document = GddDocumentRecord(
                    project_id=project_id,
                    source_version_id=source_version_id,
                    title=source_version.title,
                    status="draft",
                    parser_version=_PARSER_VERSION,
                    created_by=actor,
                )
                session.add(document)
                session.flush()
                stack: list[tuple[int, UUID]] = []
                for item in chapters:
                    while stack and stack[-1][0] >= item["heading_level"]:
                        stack.pop()
                    chapter = GddChapterRecord(
                        document_id=document.id,
                        parent_chapter_id=stack[-1][1] if stack else None,
                        **item,
                    )
                    session.add(chapter)
                    session.flush()
                    stack.append((item["heading_level"], chapter.id))
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="gdd.document_structured",
                        actor_type="system",
                        actor_id="design.gdd_architect",
                        payload={
                            "document_id": str(document.id),
                            "source_version_id": str(source_version_id),
                            "chapter_count": len(chapters),
                            "parser_version": _PARSER_VERSION,
                            "requested_by": actor,
                        },
                    )
                )
                document_id = document.id
                created = True
        return self.get_document(project_id, document_id), created

    def list_documents(self, project_id: UUID) -> list[dict[str, object]]:
        with self._sessions() as session:
            records = list(
                session.scalars(
                    select(GddDocumentRecord)
                    .where(GddDocumentRecord.project_id == project_id)
                    .order_by(GddDocumentRecord.updated_at.desc())
                )
            )
            return [self._summary(session, item) for item in records]

    def get_document(self, project_id: UUID, document_id: UUID) -> dict[str, object]:
        with self._sessions() as session:
            document = self._document(session, project_id, document_id)
            chapters = list(
                session.scalars(
                    select(GddChapterRecord)
                    .where(GddChapterRecord.document_id == document.id)
                    .order_by(GddChapterRecord.ordinal)
                )
            )
            assumptions = list(
                session.scalars(
                    select(GddAssumptionRecord)
                    .where(GddAssumptionRecord.document_id == document.id)
                    .order_by(GddAssumptionRecord.created_at)
                )
            )
            revisions = list(
                session.scalars(
                    select(GddRevisionRecord)
                    .where(GddRevisionRecord.document_id == document.id)
                    .order_by(GddRevisionRecord.revision_number.desc())
                )
            )
            return {
                **self._summary(session, document),
                "chapters": [self._chapter(item) for item in chapters],
                "assumptions": [self._assumption(item) for item in assumptions],
                "revisions": [self._revision(item) for item in revisions],
            }

    def add_assumption(
        self,
        *,
        project_id: UUID,
        document_id: UUID,
        chapter_id: UUID | None,
        statement: str,
        rationale: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        clean_statement = self._clean(statement, "statement", 2000)
        clean_rationale = self._clean(rationale, "rationale", 2000)
        clean_actor = self._clean(actor_id, "actor", 120)
        clean_command = self._clean(command_key, "idempotency key", 160)
        with self._sessions.begin() as session:
            document = self._document(session, project_id, document_id)
            existing = session.scalar(
                select(GddAssumptionRecord).where(
                    GddAssumptionRecord.document_id == document.id,
                    GddAssumptionRecord.command_key == clean_command,
                )
            )
            if existing is not None:
                if (
                    existing.chapter_id != chapter_id
                    or existing.statement != clean_statement
                    or existing.rationale != clean_rationale
                ):
                    raise GddError("idempotency key was reused for a different assumption")
                return self._assumption(existing), False
            if (
                chapter_id is not None
                and session.scalar(
                    select(GddChapterRecord.id).where(
                        GddChapterRecord.id == chapter_id,
                        GddChapterRecord.document_id == document.id,
                    )
                )
                is None
            ):
                raise GddError("GDD chapter not found")
            record = GddAssumptionRecord(
                document_id=document.id,
                chapter_id=chapter_id,
                statement=clean_statement,
                rationale=clean_rationale,
                status="proposed",
                command_key=clean_command,
                created_by=clean_actor,
            )
            session.add(record)
            session.flush()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="gdd.assumption_proposed",
                    actor_type="human",
                    actor_id=clean_actor,
                    payload={
                        "document_id": str(document.id),
                        "assumption_id": str(record.id),
                        "chapter_id": str(chapter_id) if chapter_id else None,
                    },
                )
            )
            result = self._assumption(record)
        return result, True

    def decide_assumption(
        self,
        *,
        project_id: UUID,
        document_id: UUID,
        assumption_id: UUID,
        decision: Literal["approved", "rejected"],
        reason: str,
        actor_id: str,
    ) -> dict[str, object]:
        clean_reason = self._clean(reason, "decision reason", 1000)
        clean_actor = self._clean(actor_id, "actor", 120)
        with self._sessions.begin() as session:
            document = self._document(session, project_id, document_id)
            assumption = session.scalar(
                select(GddAssumptionRecord)
                .where(
                    GddAssumptionRecord.id == assumption_id,
                    GddAssumptionRecord.document_id == document.id,
                )
                .with_for_update()
            )
            if assumption is None:
                raise GddError("GDD assumption not found")
            if assumption.status != "proposed":
                if assumption.status == decision:
                    return self._assumption(assumption)
                raise GddError("decided GDD assumptions are immutable")
            assumption.status = decision
            assumption.decided_by = clean_actor
            assumption.decision_reason = clean_reason
            assumption.decided_at = utc_now()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="gdd.assumption_decided",
                    actor_type="human",
                    actor_id=clean_actor,
                    payload={
                        "document_id": str(document.id),
                        "assumption_id": str(assumption.id),
                        "decision": decision,
                    },
                )
            )
            result = self._assumption(assumption)
        return result

    def approve_revision(
        self,
        *,
        project_id: UUID,
        document_id: UUID,
        notes: str | None,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        clean_actor = self._clean(actor_id, "actor", 120)
        clean_command = self._clean(command_key, "idempotency key", 160)
        clean_notes = self._clean(notes, "notes", 2000) if notes else None
        with self._sessions.begin() as session:
            document = self._document(session, project_id, document_id, lock=True)
            existing_command = session.scalar(
                select(GddRevisionRecord).where(
                    GddRevisionRecord.document_id == document.id,
                    GddRevisionRecord.command_key == clean_command,
                )
            )
            chapters = list(
                session.scalars(
                    select(GddChapterRecord)
                    .where(GddChapterRecord.document_id == document.id)
                    .order_by(GddChapterRecord.ordinal)
                )
            )
            assumptions = list(
                session.scalars(
                    select(GddAssumptionRecord)
                    .where(GddAssumptionRecord.document_id == document.id)
                    .order_by(GddAssumptionRecord.created_at)
                )
            )
            if not chapters:
                raise GddError("GDD has no structured chapters")
            if any(item.status == "proposed" for item in assumptions):
                raise GddError("all GDD assumptions must be decided before approval")
            manifest = {
                "schema_version": "gdd-revision-v1",
                "source_version_id": str(document.source_version_id),
                "parser_version": document.parser_version,
                "chapters": [self._chapter(item) for item in chapters],
                "assumptions": [self._assumption(item) for item in assumptions],
            }
            encoded = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            content_sha256 = hashlib.sha256(encoded).hexdigest()
            if existing_command is not None:
                if existing_command.content_sha256 != content_sha256:
                    raise GddError("idempotency key was reused for a different GDD state")
                return self._revision(existing_command), False
            latest = session.scalar(
                select(GddRevisionRecord)
                .where(GddRevisionRecord.document_id == document.id)
                .order_by(GddRevisionRecord.revision_number.desc())
                .limit(1)
            )
            if latest is not None and latest.content_sha256 == content_sha256:
                return self._revision(latest), False
            revision_number = (
                int(
                    session.scalar(
                        select(func.count(GddRevisionRecord.id)).where(
                            GddRevisionRecord.document_id == document.id
                        )
                    )
                    or 0
                )
                + 1
            )
            revision = GddRevisionRecord(
                document_id=document.id,
                revision_number=revision_number,
                manifest=manifest,
                content_sha256=content_sha256,
                notes=clean_notes,
                command_key=clean_command,
                approved_by=clean_actor,
            )
            session.add(revision)
            session.flush()
            document.status = "approved"
            document.updated_at = utc_now()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="gdd.revision_approved",
                    actor_type="human",
                    actor_id=clean_actor,
                    payload={
                        "document_id": str(document.id),
                        "revision_id": str(revision.id),
                        "revision_number": revision_number,
                        "content_sha256": revision.content_sha256,
                    },
                )
            )
            result = self._revision(revision)
        return result, True

    def _load_text(self, session: Session, version: SourceVersionRecord) -> str:
        stored = session.scalar(
            select(StoredObjectRecord)
            .join(SourceAssetRecord, SourceAssetRecord.stored_object_id == StoredObjectRecord.id)
            .where(
                SourceAssetRecord.source_version_id == version.id,
                SourceAssetRecord.role == "normalized_text",
            )
        )
        if stored is None or stored.sha256 != version.normalized_text_sha256:
            raise GddError("verified normalized GDD text is unavailable")
        with self._storage.open(stored.object_key) as handle:
            payload = handle.read()
        if hashlib.sha256(payload).hexdigest() != stored.sha256:
            raise GddError("stored GDD text failed integrity verification")
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GddError("stored GDD text is not UTF-8") from error

    @staticmethod
    def _parse(text: str) -> list[dict[str, object]]:
        matches = list(_HEADING.finditer(text))
        if not matches:
            content = text.strip()
            if not content:
                raise GddError("GDD content is blank")
            start = text.index(content)
            end = start + len(content)
            return [
                {
                    "ordinal": 0,
                    "heading_level": 1,
                    "title": "Document",
                    "start_offset": start,
                    "end_offset": end,
                    "content": content,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            ]
        result: list[dict[str, object]] = []
        for ordinal, match in enumerate(matches):
            end = matches[ordinal + 1].start() if ordinal + 1 < len(matches) else len(text)
            content = text[match.start() : end].rstrip()
            result.append(
                {
                    "ordinal": ordinal,
                    "heading_level": len(match.group(1)),
                    "title": match.group(2).strip()[:500],
                    "start_offset": match.start(),
                    "end_offset": match.start() + len(content),
                    "content": content,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            )
        return result

    @staticmethod
    def _clean(value: str | None, label: str, maximum: int) -> str:
        clean = " ".join((value or "").split())
        if not clean or len(clean) > maximum:
            raise GddError(f"{label} must contain 1 to {maximum} characters")
        return clean

    @staticmethod
    def _document(
        session: Session,
        project_id: UUID,
        document_id: UUID,
        *,
        lock: bool = False,
    ) -> GddDocumentRecord:
        statement = select(GddDocumentRecord).where(
            GddDocumentRecord.id == document_id,
            GddDocumentRecord.project_id == project_id,
        )
        if lock:
            statement = statement.with_for_update()
        document = session.scalar(statement)
        if document is None:
            raise GddError("GDD document not found")
        return document

    @staticmethod
    def _summary(session: Session, item: GddDocumentRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "project_id": str(item.project_id),
            "source_version_id": str(item.source_version_id),
            "title": item.title,
            "status": item.status,
            "parser_version": item.parser_version,
            "chapter_count": int(
                session.scalar(
                    select(func.count(GddChapterRecord.id)).where(
                        GddChapterRecord.document_id == item.id
                    )
                )
                or 0
            ),
            "assumption_count": int(
                session.scalar(
                    select(func.count(GddAssumptionRecord.id)).where(
                        GddAssumptionRecord.document_id == item.id
                    )
                )
                or 0
            ),
            "revision_count": int(
                session.scalar(
                    select(func.count(GddRevisionRecord.id)).where(
                        GddRevisionRecord.document_id == item.id
                    )
                )
                or 0
            ),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    def _chapter(item: GddChapterRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "parent_chapter_id": str(item.parent_chapter_id) if item.parent_chapter_id else None,
            "ordinal": item.ordinal,
            "heading_level": item.heading_level,
            "title": item.title,
            "start_offset": item.start_offset,
            "end_offset": item.end_offset,
            "content": item.content,
            "content_sha256": item.content_sha256,
        }

    @staticmethod
    def _assumption(item: GddAssumptionRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "chapter_id": str(item.chapter_id) if item.chapter_id else None,
            "statement": item.statement,
            "rationale": item.rationale,
            "status": item.status,
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat(),
            "decided_by": item.decided_by,
            "decision_reason": item.decision_reason,
            "decided_at": item.decided_at.isoformat() if item.decided_at else None,
        }

    @staticmethod
    def _revision(item: GddRevisionRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "revision_number": item.revision_number,
            "content_sha256": item.content_sha256,
            "notes": item.notes,
            "approved_by": item.approved_by,
            "created_at": item.created_at.isoformat(),
            "manifest": item.manifest,
        }
