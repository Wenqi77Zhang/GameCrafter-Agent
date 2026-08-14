"""Project-scoped delivery service for the Knowledge workspace."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    KnowledgeEntityRecord,
    KnowledgeEntityRevisionRecord,
    ProjectRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
)


class KnowledgeWorkspaceConflictError(ValueError):
    """Raised when a correction conflicts with immutable entity history."""


class KnowledgeWorkspaceNotFoundError(LookupError):
    """Raised when a project-scoped Knowledge workspace record is absent."""


class DatabaseKnowledgeWorkspaceService:
    """Create stable entities and expose append-only corrections and source versions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_entities(
        self,
        project_id: UUID,
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            entities = list(
                session.scalars(
                    select(KnowledgeEntityRecord)
                    .where(KnowledgeEntityRecord.project_id == project_id)
                    .order_by(KnowledgeEntityRecord.created_at, KnowledgeEntityRecord.id)
                )
            )
            items = [self._entity(session, entity) for entity in entities]
            return (
                items
                if include_archived
                else [item for item in items if item["status"] == "active"]
            )

    def create_entity(
        self,
        *,
        project_id: UUID,
        display_name: str,
        aliases: list[str],
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        name = _clean_text(display_name)
        cleaned_aliases = _clean_aliases(name, aliases)
        with self._session_factory.begin() as session:
            project = self._require_project(session, project_id)
            existing_entities = list(
                session.scalars(
                    select(KnowledgeEntityRecord)
                    .where(
                        KnowledgeEntityRecord.project_id == project_id,
                        KnowledgeEntityRecord.entity_type == "game",
                    )
                    .with_for_update()
                )
            )
            for existing in existing_entities:
                item = self._entity(session, existing)
                if item["status"] == "active":
                    if _same_identity(item, name, cleaned_aliases):
                        return item, False
                    if _identity_overlap(item, name, cleaned_aliases):
                        raise KnowledgeWorkspaceConflictError(
                            "knowledge entity may duplicate an existing active entity"
                        )

            canonical_key = self._next_game_key(
                project=project,
                display_name=name,
                aliases=cleaned_aliases,
                existing=existing_entities,
            )
            entity = KnowledgeEntityRecord(
                project_id=project_id,
                entity_type="game",
                canonical_key=canonical_key,
                display_name=name,
                aliases=cleaned_aliases,
                details={},
            )
            session.add(entity)
            session.flush()
            revision = KnowledgeEntityRevisionRecord(
                entity_id=entity.id,
                project_id=project_id,
                revision_number=1,
                display_name=name,
                aliases=cleaned_aliases,
                status="active",
                change_reason="entity created",
                actor_id=actor_id,
            )
            session.add(revision)
            session.flush()
            self._audit(
                session,
                project_id=project_id,
                event_type="knowledge.entity_created",
                actor_id=actor_id,
                entity=entity,
                revision=revision,
            )
            return self._entity_from(entity, revision), True

    def correct_entity(
        self,
        *,
        project_id: UUID,
        entity_id: UUID,
        display_name: str,
        aliases: list[str],
        change_reason: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        name = _clean_text(display_name)
        reason = _clean_text(change_reason)
        cleaned_aliases = _clean_aliases(name, aliases)
        with self._session_factory.begin() as session:
            self._require_project(session, project_id)
            entity = self._require_entity(session, project_id, entity_id, lock=True)
            latest = self._latest_revision(session, entity.id)
            current = self._entity_from(entity, latest)
            if current["status"] == "archived":
                raise KnowledgeWorkspaceConflictError("archived entity cannot be corrected")
            if _same_identity(current, name, cleaned_aliases):
                return current, False
            revision = KnowledgeEntityRevisionRecord(
                entity_id=entity.id,
                project_id=project_id,
                revision_number=(latest.revision_number if latest is not None else 0) + 1,
                display_name=name,
                aliases=cleaned_aliases,
                status="active",
                change_reason=reason,
                actor_id=actor_id,
            )
            session.add(revision)
            session.flush()
            self._audit(
                session,
                project_id=project_id,
                event_type="knowledge.entity_corrected",
                actor_id=actor_id,
                entity=entity,
                revision=revision,
            )
            return self._entity_from(entity, revision), True

    def archive_entity(
        self,
        *,
        project_id: UUID,
        entity_id: UUID,
        change_reason: str,
        actor_id: str,
    ) -> tuple[dict[str, Any], bool]:
        reason = _clean_text(change_reason)
        with self._session_factory.begin() as session:
            self._require_project(session, project_id)
            entity = self._require_entity(session, project_id, entity_id, lock=True)
            latest = self._latest_revision(session, entity.id)
            current = self._entity_from(entity, latest)
            if current["status"] == "archived":
                return current, False
            revision = KnowledgeEntityRevisionRecord(
                entity_id=entity.id,
                project_id=project_id,
                revision_number=(latest.revision_number if latest is not None else 0) + 1,
                display_name=str(current["display_name"]),
                aliases=list(current["aliases"]),
                status="archived",
                change_reason=reason,
                actor_id=actor_id,
            )
            session.add(revision)
            session.flush()
            self._audit(
                session,
                project_id=project_id,
                event_type="knowledge.entity_archived",
                actor_id=actor_id,
                entity=entity,
                revision=revision,
            )
            return self._entity_from(entity, revision), True

    def list_entity_revisions(
        self,
        *,
        project_id: UUID,
        entity_id: UUID,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            entity = self._require_entity(session, project_id, entity_id)
            revisions = list(
                session.scalars(
                    select(KnowledgeEntityRevisionRecord)
                    .where(KnowledgeEntityRevisionRecord.entity_id == entity.id)
                    .order_by(KnowledgeEntityRevisionRecord.revision_number)
                )
            )
            if not revisions:
                return [self._synthetic_revision(entity)]
            return [self._revision(item) for item in revisions]

    def list_source_versions(self, project_id: UUID) -> list[dict[str, Any]]:
        latest_number = (
            select(func.max(SourceVersionRecord.version_number))
            .where(SourceVersionRecord.source_id == SourceRecord.id)
            .correlate(SourceRecord)
            .scalar_subquery()
        )
        normalized_assets = (
            select(func.count(SourceAssetRecord.id))
            .where(
                SourceAssetRecord.source_version_id == SourceVersionRecord.id,
                SourceAssetRecord.role == "normalized_text",
                SourceAssetRecord.ordinal == 0,
            )
            .correlate(SourceVersionRecord)
            .scalar_subquery()
        )
        with self._session_factory() as session:
            self._require_project(session, project_id)
            rows = session.execute(
                select(
                    SourceRecord,
                    SourceVersionRecord,
                    latest_number.label("latest_number"),
                    normalized_assets.label("normalized_assets"),
                )
                .join(SourceVersionRecord, SourceVersionRecord.source_id == SourceRecord.id)
                .where(SourceRecord.project_id == project_id)
                .order_by(SourceRecord.updated_at.desc(), SourceVersionRecord.version_number.desc())
            ).all()
            return [
                {
                    "id": str(version.id),
                    "source_id": str(source.id),
                    "version_number": version.version_number,
                    "is_latest": version.version_number == latest,
                    "title": version.title,
                    "url": source.canonical_url,
                    "site": source.site_key,
                    "locale": source.locale,
                    "region": source.region,
                    "source_type": source.source_type,
                    "source_status": source.status,
                    "published_at": _iso(version.published_at),
                    "fetched_at": _iso(version.fetched_at),
                    "capture_method": version.capture_method,
                    "change_kind": version.change_kind,
                    "normalized_text_sha256": version.normalized_text_sha256,
                    "evidence_fingerprint_sha256": version.evidence_fingerprint_sha256,
                    "normalized_text_available": normalized_count == 1,
                }
                for source, version, latest, normalized_count in rows
            ]

    @staticmethod
    def _require_project(session: Session, project_id: UUID) -> ProjectRecord:
        project = session.get(ProjectRecord, project_id)
        if project is None:
            raise KnowledgeWorkspaceNotFoundError("project not found")
        return project

    @staticmethod
    def _require_entity(
        session: Session,
        project_id: UUID,
        entity_id: UUID,
        *,
        lock: bool = False,
    ) -> KnowledgeEntityRecord:
        statement = select(KnowledgeEntityRecord).where(
            KnowledgeEntityRecord.id == entity_id,
            KnowledgeEntityRecord.project_id == project_id,
        )
        if lock:
            statement = statement.with_for_update()
        entity = session.scalar(statement)
        if entity is None:
            raise KnowledgeWorkspaceNotFoundError("knowledge entity not found")
        return entity

    @staticmethod
    def _latest_revision(
        session: Session,
        entity_id: UUID,
    ) -> KnowledgeEntityRevisionRecord | None:
        return session.scalar(
            select(KnowledgeEntityRevisionRecord)
            .where(KnowledgeEntityRevisionRecord.entity_id == entity_id)
            .order_by(KnowledgeEntityRevisionRecord.revision_number.desc())
            .limit(1)
        )

    def _entity(self, session: Session, entity: KnowledgeEntityRecord) -> dict[str, Any]:
        return self._entity_from(entity, self._latest_revision(session, entity.id))

    @staticmethod
    def _entity_from(
        entity: KnowledgeEntityRecord,
        revision: KnowledgeEntityRevisionRecord | None,
    ) -> dict[str, Any]:
        return {
            "id": str(entity.id),
            "project_id": str(entity.project_id),
            "entity_type": entity.entity_type,
            "canonical_key": entity.canonical_key,
            "display_name": revision.display_name if revision is not None else entity.display_name,
            "aliases": list(revision.aliases if revision is not None else entity.aliases),
            "status": revision.status if revision is not None else "active",
            "revision_number": revision.revision_number if revision is not None else 0,
            "created_at": _iso(entity.created_at),
            "revised_at": _iso(revision.created_at) if revision is not None else None,
        }

    @staticmethod
    def _revision(revision: KnowledgeEntityRevisionRecord) -> dict[str, Any]:
        return {
            "id": str(revision.id),
            "entity_id": str(revision.entity_id),
            "project_id": str(revision.project_id),
            "revision_number": revision.revision_number,
            "display_name": revision.display_name,
            "aliases": list(revision.aliases),
            "status": revision.status,
            "change_reason": revision.change_reason,
            "actor_id": revision.actor_id,
            "created_at": _iso(revision.created_at),
        }

    @staticmethod
    def _synthetic_revision(entity: KnowledgeEntityRecord) -> dict[str, Any]:
        return {
            "id": str(entity.id),
            "entity_id": str(entity.id),
            "project_id": str(entity.project_id),
            "revision_number": 0,
            "display_name": entity.display_name,
            "aliases": list(entity.aliases),
            "status": "active",
            "change_reason": "legacy entity without revision history",
            "actor_id": "system",
            "created_at": _iso(entity.created_at),
        }

    @staticmethod
    def _next_game_key(
        *,
        project: ProjectRecord,
        display_name: str,
        aliases: list[str],
        existing: list[KnowledgeEntityRecord],
    ) -> str:
        used = {item.canonical_key for item in existing}
        if not existing:
            project_key = f"game:{project.slug}"
            if project_key not in used:
                return project_key
        slug = _identity_slug([*aliases, display_name])
        candidate = f"game:{slug}"
        if candidate not in used:
            return candidate
        suffix = sha256(
            "\0".join([display_name.casefold(), *(item.casefold() for item in aliases)]).encode(
                "utf-8"
            )
        ).hexdigest()[:8]
        candidate = f"game:{slug[:70]}-{suffix}"
        if candidate in used:
            raise KnowledgeWorkspaceConflictError("knowledge entity identity already exists")
        return candidate

    @staticmethod
    def _audit(
        session: Session,
        *,
        project_id: UUID,
        event_type: str,
        actor_id: str,
        entity: KnowledgeEntityRecord,
        revision: KnowledgeEntityRevisionRecord,
    ) -> None:
        session.add(
            AuditEventRecord(
                project_id=project_id,
                event_type=event_type,
                actor_type="human",
                actor_id=actor_id,
                payload={
                    "entity_id": str(entity.id),
                    "entity_type": entity.entity_type,
                    "canonical_key": entity.canonical_key,
                    "revision_number": revision.revision_number,
                    "status": revision.status,
                },
            )
        )


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _clean_aliases(display_name: str, aliases: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen = {display_name.casefold()}
    for value in aliases:
        alias = _clean_text(value)
        folded = alias.casefold()
        if not alias or folded in seen:
            continue
        seen.add(folded)
        cleaned.append(alias)
    return cleaned


def _same_identity(item: dict[str, Any], display_name: str, aliases: list[str]) -> bool:
    return str(item["display_name"]).casefold() == display_name.casefold() and {
        str(alias).casefold() for alias in item["aliases"]
    } == {alias.casefold() for alias in aliases}


def _identity_overlap(item: dict[str, Any], display_name: str, aliases: list[str]) -> bool:
    existing = {
        str(item["display_name"]).casefold(),
        *(str(alias).casefold() for alias in item["aliases"]),
    }
    requested = {display_name.casefold(), *(alias.casefold() for alias in aliases)}
    return not existing.isdisjoint(requested)


def _identity_slug(values: list[str]) -> str:
    for value in values:
        match = re.match(r"^([A-Z0-9]{2,12})(?:\b|\s*:)", value.strip())
        if match is not None:
            return match.group(1).lower()
    for value in values:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
        if slug:
            return slug[:80]
    return sha256("\0".join(values).encode("utf-8")).hexdigest()[:12]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
