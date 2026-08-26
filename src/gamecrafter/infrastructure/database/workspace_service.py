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
    KnowledgeClaimRecord,
    KnowledgeSnapshotRecord,
    MarketingTaskRecord,
    ProjectRecord,
    ScriptExportRecord,
    ScriptFinalReviewRecord,
    ScriptRunRecord,
    ScriptVersionRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    TopicReviewRecord,
    TrendSignalRecord,
    WorkflowJobRecord,
    WorkflowRunRecord,
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

    def project_overview(self, project_id: UUID) -> dict[str, Any]:
        """Return a compact, truthful progress and operations read model."""

        with self._session_factory() as session:
            self._require_project(session, project_id)

            def count(statement: Select[tuple[Any]]) -> int:
                return int(session.scalar(statement) or 0)

            source_count = count(
                select(func.count(SourceRecord.id)).where(SourceRecord.project_id == project_id)
            )
            version_count = count(
                select(func.count(SourceVersionRecord.id))
                .select_from(SourceVersionRecord)
                .join(SourceRecord, SourceRecord.id == SourceVersionRecord.source_id)
                .where(SourceRecord.project_id == project_id)
            )
            claim_count = count(
                select(func.count(KnowledgeClaimRecord.id)).where(
                    KnowledgeClaimRecord.project_id == project_id
                )
            )
            snapshot_count = count(
                select(func.count(KnowledgeSnapshotRecord.id)).where(
                    KnowledgeSnapshotRecord.project_id == project_id
                )
            )
            signal_count = count(
                select(func.count(TrendSignalRecord.id)).where(
                    TrendSignalRecord.project_id == project_id
                )
            )
            task_count = count(
                select(func.count(MarketingTaskRecord.id)).where(
                    MarketingTaskRecord.project_id == project_id
                )
            )
            approved_topic_count = count(
                select(func.count(TopicReviewRecord.id))
                .select_from(TopicReviewRecord)
                .join(MarketingTaskRecord, MarketingTaskRecord.id == TopicReviewRecord.task_id)
                .where(
                    MarketingTaskRecord.project_id == project_id,
                    TopicReviewRecord.decision == "approve",
                )
            )
            script_run_count = count(
                select(func.count(ScriptRunRecord.id)).where(
                    ScriptRunRecord.project_id == project_id
                )
            )
            script_version_count = count(
                select(func.count(ScriptVersionRecord.id))
                .select_from(ScriptVersionRecord)
                .join(ScriptRunRecord, ScriptRunRecord.id == ScriptVersionRecord.run_id)
                .where(ScriptRunRecord.project_id == project_id)
            )
            final_approval_count = count(
                select(func.count(ScriptFinalReviewRecord.id))
                .select_from(ScriptFinalReviewRecord)
                .join(ScriptRunRecord, ScriptRunRecord.id == ScriptFinalReviewRecord.run_id)
                .where(
                    ScriptRunRecord.project_id == project_id,
                    ScriptFinalReviewRecord.decision == "approve",
                )
            )
            export_count = count(
                select(func.count(ScriptExportRecord.id))
                .select_from(ScriptExportRecord)
                .join(ScriptRunRecord, ScriptRunRecord.id == ScriptExportRecord.run_id)
                .where(ScriptRunRecord.project_id == project_id)
            )
            succeeded_runs = count(
                select(func.count(WorkflowRunRecord.id)).where(
                    WorkflowRunRecord.project_id == project_id,
                    WorkflowRunRecord.status == "succeeded",
                )
            )
            attention_runs = count(
                select(func.count(WorkflowRunRecord.id)).where(
                    WorkflowRunRecord.project_id == project_id,
                    WorkflowRunRecord.status == "needs_attention",
                )
            )
            active_runs = count(
                select(func.count(WorkflowRunRecord.id)).where(
                    WorkflowRunRecord.project_id == project_id,
                    WorkflowRunRecord.status.in_(("queued", "running", "retry_wait")),
                )
            )

            stages = [
                self._stage("sources", version_count > 0, source_count > 0),
                self._stage("knowledge", snapshot_count > 0, claim_count > 0),
                self._stage(
                    "marketing", approved_topic_count > 0, task_count > 0 or signal_count > 0
                ),
                self._stage("creation", final_approval_count > 0, script_run_count > 0),
                self._stage("delivery", export_count > 0, final_approval_count > 0),
            ]
            next_action = next(
                (stage["key"] for stage in stages if stage["status"] != "complete"), "complete"
            )
            return {
                "project_id": str(project_id),
                "release": "M12-local",
                "next_action": next_action,
                "stages": stages,
                "metrics": {
                    "sources": source_count,
                    "evidence_versions": version_count,
                    "candidate_claims": claim_count,
                    "published_snapshots": snapshot_count,
                    "verified_trend_signals": signal_count,
                    "marketing_tasks": task_count,
                    "approved_topics": approved_topic_count,
                    "script_runs": script_run_count,
                    "script_versions": script_version_count,
                    "final_approvals": final_approval_count,
                    "exports": export_count,
                    "successful_runs": succeeded_runs,
                    "attention_runs": attention_runs,
                    "active_runs": active_runs,
                    "api_cost_usd": 0,
                },
            }

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
                select(WorkflowRunRecord).where(
                    WorkflowRunRecord.project_id == project_id,
                    WorkflowRunRecord.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                job = session.scalar(
                    select(WorkflowJobRecord)
                    .where(WorkflowJobRecord.run_id == existing.id)
                    .order_by(WorkflowJobRecord.created_at, WorkflowJobRecord.id)
                    .limit(1)
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

            run = WorkflowRunRecord(
                project_id=project_id,
                idempotency_key=idempotency_key,
                workflow_kind=task_type,
            )
            session.add(run)
            session.flush()
            session.add(
                WorkflowJobRecord(
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
            initial_task_type = (
                select(WorkflowJobRecord.task_type)
                .where(WorkflowJobRecord.run_id == WorkflowRunRecord.id)
                .order_by(WorkflowJobRecord.created_at, WorkflowJobRecord.id)
                .limit(1)
                .scalar_subquery()
            )
            rows = session.execute(
                select(WorkflowRunRecord, initial_task_type.label("initial_task_type"))
                .where(WorkflowRunRecord.project_id == project_id)
                .order_by(WorkflowRunRecord.created_at.desc())
            ).all()
            return [self._run(run, task_type) for run, task_type in rows]

    def get_run(self, run_id: UUID) -> dict[str, Any]:
        with self._session_factory() as session:
            initial_task_type = (
                select(WorkflowJobRecord.task_type)
                .where(WorkflowJobRecord.run_id == WorkflowRunRecord.id)
                .order_by(WorkflowJobRecord.created_at, WorkflowJobRecord.id)
                .limit(1)
                .scalar_subquery()
            )
            row = session.execute(
                select(WorkflowRunRecord, initial_task_type.label("initial_task_type")).where(
                    WorkflowRunRecord.id == run_id
                )
            ).one_or_none()
            if row is None:
                raise WorkspaceNotFoundError("run not found")
            return self._run(row[0], row[1])

    def retry_run(
        self, *, run_id: UUID, command_key: str, actor_id: str
    ) -> tuple[dict[str, Any], bool]:
        """Explicitly requeue failed jobs after a human has addressed the visible cause."""

        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            run = session.get(WorkflowRunRecord, run_id, with_for_update=True)
            if run is None:
                raise WorkspaceNotFoundError("run not found")
            retry_events = session.scalars(
                select(AuditEventRecord).where(
                    AuditEventRecord.run_id == run_id,
                    AuditEventRecord.event_type == "run.retried",
                )
            ).all()
            if any(event.payload.get("command_key") == command_key for event in retry_events):
                task_type = session.scalar(
                    select(WorkflowJobRecord.task_type)
                    .where(WorkflowJobRecord.run_id == run_id)
                    .order_by(WorkflowJobRecord.created_at, WorkflowJobRecord.id)
                    .limit(1)
                )
                return self._run(run, task_type), False
            if run.status != "needs_attention":
                raise WorkspaceConflictError("only a run needing attention can be retried")
            failed_jobs = session.scalars(
                select(WorkflowJobRecord)
                .where(
                    WorkflowJobRecord.run_id == run_id,
                    WorkflowJobRecord.status == "failed",
                )
                .with_for_update()
            ).all()
            if not failed_jobs:
                raise WorkspaceConflictError("run has no failed job to retry")
            for job in failed_jobs:
                job.status = "queued"
                job.attempts = 0
                job.available_at = now
                job.lease_owner = None
                job.lease_expires_at = None
                job.last_error_code = None
                job.last_error_detail = None
                job.updated_at = now
            run.status = "queued"
            run.version += 1
            run.finished_at = None
            run.last_error_code = None
            run.last_error_detail = None
            run.updated_at = now
            session.add(
                AuditEventRecord(
                    project_id=run.project_id,
                    run_id=run.id,
                    event_type="run.retried",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "command_key": command_key,
                        "requeued_jobs": len(failed_jobs),
                    },
                )
            )
            return self._run(run, failed_jobs[0].task_type), True

    def events_after(self, run_id: UUID, cursor: UUID | None) -> tuple[list[dict[str, Any]], bool]:
        with self._session_factory() as session:
            run = session.get(WorkflowRunRecord, run_id)
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
    def _stage(key: str, complete: bool, started: bool) -> dict[str, str]:
        status = "complete" if complete else "in_progress" if started else "not_started"
        return {"key": key, "status": status}

    @staticmethod
    def _run(row: WorkflowRunRecord, task_type: str | None) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "workflow_kind": row.workflow_kind,
            "task_type": task_type or row.workflow_kind,
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
