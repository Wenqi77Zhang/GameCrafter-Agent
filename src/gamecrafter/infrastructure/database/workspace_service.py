"""Project-scoped commands and read models for the source workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    DiscoveryCandidateRecord,
    IngestionJobRecord,
    IngestionRunRecord,
    ProjectRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
)


class WorkspaceConflictError(ValueError):
    """Raised when an idempotency key or candidate state conflicts."""


class WorkspaceNotFoundError(LookupError):
    """Raised when a project-scoped entity does not exist."""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class DatabaseWorkspaceService:
    """Small transactional boundary used by the local workspace API."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_projects(self) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(select(ProjectRecord).order_by(ProjectRecord.created_at)).all()
            return [
                {
                    "id": str(row.id),
                    "slug": row.slug,
                    "name": row.name,
                    "default_locale": row.default_locale,
                    "created_at": _iso(row.created_at),
                }
                for row in rows
            ]

    def create_project(
        self, *, slug: str, name: str, default_locale: str, actor_id: str
    ) -> tuple[dict[str, Any], bool]:
        with self._session_factory.begin() as session:
            existing = session.scalar(select(ProjectRecord).where(ProjectRecord.slug == slug))
            if existing is not None:
                return self._project(existing), False
            project = ProjectRecord(slug=slug, name=name, default_locale=default_locale)
            session.add(project)
            session.flush()
            session.add(
                AuditEventRecord(
                    project_id=project.id,
                    event_type="project.created",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={"slug": slug, "default_locale": default_locale},
                )
            )
            return self._project(project), True

    def enqueue(
        self,
        *,
        project_id: UUID,
        idempotency_key: str,
        task_type: str,
        payload: dict[str, Any],
        actor_id: str,
        candidate_id: UUID | None = None,
    ) -> tuple[dict[str, Any], bool]:
        with self._session_factory.begin() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise WorkspaceNotFoundError("project not found")
            existing = session.scalar(
                select(IngestionRunRecord).where(
                    IngestionRunRecord.project_id == project_id,
                    IngestionRunRecord.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                job = session.scalar(
                    select(IngestionJobRecord).where(IngestionJobRecord.run_id == existing.id)
                )
                if job is None or job.task_type != task_type or job.payload != payload:
                    raise WorkspaceConflictError(
                        "idempotency key was already used for a different request"
                    )
                return self._run(existing, job.task_type), False

            candidate: DiscoveryCandidateRecord | None = None
            if candidate_id is not None:
                candidate = session.scalar(
                    select(DiscoveryCandidateRecord)
                    .where(DiscoveryCandidateRecord.id == candidate_id)
                    .with_for_update()
                )
                if candidate is None or candidate.project_id != project_id:
                    raise WorkspaceNotFoundError("candidate not found")
                if candidate.status != "discovered":
                    raise WorkspaceConflictError("candidate is no longer available for import")
                candidate.status = "selected"
                candidate.selected_at = datetime.now(UTC)

            run = IngestionRunRecord(
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            session.add(run)
            session.flush()
            session.add(
                IngestionJobRecord(
                    run_id=run.id,
                    task_type=task_type,
                    payload=payload,
                    max_attempts=3,
                    available_at=datetime.now(UTC),
                )
            )
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=run.id,
                    event_type="run.queued",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "task_type": task_type,
                        **({"candidate_id": str(candidate_id)} if candidate_id else {}),
                    },
                )
            )
            return self._run(run, task_type), True

    def list_candidates(self, project_id: UUID) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            rows = session.scalars(
                select(DiscoveryCandidateRecord)
                .where(DiscoveryCandidateRecord.project_id == project_id)
                .order_by(
                    DiscoveryCandidateRecord.published_at.desc().nullslast(),
                    DiscoveryCandidateRecord.discovered_at.desc(),
                )
            ).all()
            return [
                {
                    "id": str(row.id),
                    "run_id": str(row.run_id),
                    "url": row.canonical_url,
                    "site": row.site_key,
                    "locale": row.locale,
                    "region": row.region,
                    "title": row.title,
                    "published_at": _iso(row.published_at),
                    "source_type": row.source_type,
                    "raw_category": row.raw_category,
                    "classification_basis": row.classification_basis,
                    "status": row.status,
                    "imported_source_id": (
                        str(row.imported_source_id) if row.imported_source_id else None
                    ),
                }
                for row in rows
            ]

    def list_sources(self, project_id: UUID) -> list[dict[str, Any]]:
        version_count = (
            select(func.count(SourceVersionRecord.id))
            .where(SourceVersionRecord.source_id == SourceRecord.id)
            .correlate(SourceRecord)
            .scalar_subquery()
        )
        asset_count = (
            select(func.count(SourceAssetRecord.id))
            .join(
                SourceVersionRecord,
                SourceVersionRecord.id == SourceAssetRecord.source_version_id,
            )
            .where(SourceVersionRecord.source_id == SourceRecord.id)
            .correlate(SourceRecord)
            .scalar_subquery()
        )
        latest_version = (
            select(func.max(SourceVersionRecord.version_number))
            .where(SourceVersionRecord.source_id == SourceRecord.id)
            .correlate(SourceRecord)
            .scalar_subquery()
        )
        statement: Select[tuple[SourceRecord, int, int, int | None]] = (
            select(SourceRecord, version_count, asset_count, latest_version)
            .where(SourceRecord.project_id == project_id)
            .order_by(SourceRecord.updated_at.desc())
        )
        with self._session_factory() as session:
            self._require_project(session, project_id)
            return [
                {
                    "id": str(source.id),
                    "url": source.canonical_url,
                    "site": source.site_key,
                    "locale": source.locale,
                    "region": source.region,
                    "source_type": source.source_type,
                    "status": source.status,
                    "version_count": versions,
                    "asset_count": assets,
                    "latest_version": latest,
                    "updated_at": _iso(source.updated_at),
                }
                for source, versions, assets, latest in session.execute(statement).all()
            ]

    def list_runs(self, project_id: UUID) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            rows = session.execute(
                select(IngestionRunRecord, IngestionJobRecord.task_type)
                .join(IngestionJobRecord, IngestionJobRecord.run_id == IngestionRunRecord.id)
                .where(IngestionRunRecord.project_id == project_id)
                .order_by(IngestionRunRecord.created_at.desc())
            ).all()
            return [self._run(run, task_type) for run, task_type in rows]

    def get_run(self, run_id: UUID) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.execute(
                select(IngestionRunRecord, IngestionJobRecord.task_type)
                .join(IngestionJobRecord, IngestionJobRecord.run_id == IngestionRunRecord.id)
                .where(IngestionRunRecord.id == run_id)
            ).one_or_none()
            if row is None:
                raise WorkspaceNotFoundError("run not found")
            return self._run(row[0], row[1])

    def events_after(self, run_id: UUID, cursor: UUID | None) -> tuple[list[dict[str, Any]], bool]:
        with self._session_factory() as session:
            run = session.get(IngestionRunRecord, run_id)
            if run is None:
                raise WorkspaceNotFoundError("run not found")
            statement = select(AuditEventRecord).where(AuditEventRecord.run_id == run_id)
            if cursor is not None:
                previous = session.get(AuditEventRecord, cursor)
                if previous is None or previous.run_id != run_id:
                    raise WorkspaceConflictError("event cursor does not belong to this run")
                statement = statement.where(
                    (AuditEventRecord.occurred_at > previous.occurred_at)
                    | (
                        (AuditEventRecord.occurred_at == previous.occurred_at)
                        & (AuditEventRecord.id > previous.id)
                    )
                )
            rows = session.scalars(
                statement.order_by(AuditEventRecord.occurred_at, AuditEventRecord.id)
            ).all()
            terminal = run.status in {"succeeded", "needs_attention", "cancelled"}
            return [
                {
                    "id": str(row.id),
                    "event_type": row.event_type,
                    "actor_type": row.actor_type,
                    "payload": row.payload,
                    "occurred_at": _iso(row.occurred_at),
                }
                for row in rows
            ], terminal

    @staticmethod
    def _project(row: ProjectRecord) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "slug": row.slug,
            "name": row.name,
            "default_locale": row.default_locale,
            "created_at": _iso(row.created_at),
        }

    @staticmethod
    def _run(row: IngestionRunRecord, task_type: str) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "task_type": task_type,
            "status": row.status,
            "checkpoint": row.checkpoint,
            "last_error_code": row.last_error_code,
            "last_error_detail": row.last_error_detail,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "finished_at": _iso(row.finished_at),
        }

    @staticmethod
    def _require_project(session: Session, project_id: UUID) -> None:
        if session.get(ProjectRecord, project_id) is None:
            raise WorkspaceNotFoundError("project not found")
