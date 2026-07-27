"""Transactional commands for creating the first durable project and run records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    IngestionJobRecord,
    IngestionRunRecord,
    ProjectRecord,
)


class DatabaseRunService:
    """Write-side persistence service used by later source commands."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_project(
        self,
        *,
        slug: str,
        name: str,
        default_locale: str = "zh-CN",
        actor_id: str = "local-user",
    ) -> UUID:
        with self._session_factory.begin() as session:
            existing = session.scalar(select(ProjectRecord).where(ProjectRecord.slug == slug))
            if existing is not None:
                return existing.id

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
            return project.id

    def enqueue_run(
        self,
        *,
        project_id: UUID,
        idempotency_key: str,
        task_type: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
        actor_id: str = "local-user",
    ) -> UUID:
        """Create one run and initial job, or return the existing idempotent run."""

        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(IngestionRunRecord).where(
                    IngestionRunRecord.project_id == project_id,
                    IngestionRunRecord.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing.id

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
                    payload=payload or {},
                    max_attempts=max_attempts,
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
                    payload={"task_type": task_type},
                )
            )
            return run.id
