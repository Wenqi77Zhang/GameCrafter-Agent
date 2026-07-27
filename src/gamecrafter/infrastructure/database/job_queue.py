"""PostgreSQL-backed job queue with leases and bounded retries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import ClaimedJob
from gamecrafter.domain.runs.state import IngestionRun, JobStatus, RunStatus
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    IngestionJobRecord,
    IngestionRunRecord,
)


class JobLeaseError(RuntimeError):
    """Raised when a worker no longer owns the job it tries to update."""


def _run_state(record: IngestionRunRecord) -> IngestionRun:
    return IngestionRun(
        status=RunStatus(record.status),
        checkpoint=record.checkpoint,
        version=record.version,
        started_at=record.started_at,
        finished_at=record.finished_at,
        last_error_code=record.last_error_code,
        last_error_detail=record.last_error_detail,
    )


def _apply_run_state(record: IngestionRunRecord, state: IngestionRun) -> None:
    record.status = state.status.value
    record.checkpoint = state.checkpoint
    record.version = state.version
    record.started_at = state.started_at
    record.finished_at = state.finished_at
    record.last_error_code = state.last_error_code
    record.last_error_detail = state.last_error_detail


def _event(
    *,
    run: IngestionRunRecord,
    event_type: str,
    worker_id: str,
    payload: dict[str, Any] | None = None,
) -> AuditEventRecord:
    return AuditEventRecord(
        project_id=run.project_id,
        run_id=run.id,
        event_type=event_type,
        actor_type="worker",
        actor_id=worker_id,
        payload=payload or {},
    )


class DatabaseJobQueue:
    """Claim and settle jobs atomically through PostgreSQL row locks."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        now = datetime.now(UTC)
        claimable: Select[tuple[IngestionJobRecord]] = (
            select(IngestionJobRecord)
            .where(
                or_(
                    and_(
                        IngestionJobRecord.status == JobStatus.QUEUED.value,
                        IngestionJobRecord.attempts < IngestionJobRecord.max_attempts,
                        IngestionJobRecord.available_at <= now,
                    ),
                    and_(
                        IngestionJobRecord.status == JobStatus.LEASED.value,
                        IngestionJobRecord.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(IngestionJobRecord.available_at, IngestionJobRecord.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        with self._session_factory.begin() as session:
            job = session.scalar(claimable)
            if job is None:
                return None

            run = session.get(IngestionRunRecord, job.run_id, with_for_update=True)
            if run is None:
                raise RuntimeError(f"job {job.id} references a missing run")

            state = _run_state(run)
            if job.status == JobStatus.LEASED.value and job.attempts >= job.max_attempts:
                job.status = JobStatus.FAILED.value
                job.lease_owner = None
                job.lease_expires_at = None
                job.last_error_code = "lease_expired"
                job.last_error_detail = "worker lease expired after the final allowed attempt"
                job.updated_at = now
                state = state.transition(
                    RunStatus.NEEDS_ATTENTION,
                    checkpoint=job.task_type,
                    error_code=job.last_error_code,
                    error_detail=job.last_error_detail,
                    at=now,
                )
                _apply_run_state(run, state)
                session.add(
                    _event(
                        run=run,
                        event_type="job.failed",
                        worker_id=worker_id,
                        payload={
                            "job_id": str(job.id),
                            "attempt": job.attempts,
                            "max_attempts": job.max_attempts,
                            "error_code": job.last_error_code,
                        },
                    )
                )
                return None

            if state.status is RunStatus.RETRY_WAIT:
                state = state.transition(RunStatus.QUEUED, checkpoint=state.checkpoint, at=now)
            if state.status is RunStatus.QUEUED:
                state = state.transition(RunStatus.RUNNING, checkpoint=job.task_type, at=now)
                _apply_run_state(run, state)

            job.status = JobStatus.LEASED.value
            job.lease_owner = worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.attempts += 1
            job.updated_at = now
            session.add(
                _event(
                    run=run,
                    event_type="job.leased",
                    worker_id=worker_id,
                    payload={"job_id": str(job.id), "attempt": job.attempts},
                )
            )
            session.flush()
            return ClaimedJob(
                id=job.id,
                run_id=job.run_id,
                task_type=job.task_type,
                payload=dict(job.payload),
                attempts=job.attempts,
                max_attempts=job.max_attempts,
            )

    def complete(self, job: ClaimedJob, *, worker_id: str) -> None:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            record, run = self._locked_job_and_run(session, job, worker_id)
            record.status = JobStatus.COMPLETED.value
            record.lease_owner = None
            record.lease_expires_at = None
            record.updated_at = now

            unfinished = session.scalar(
                select(func.count())
                .select_from(IngestionJobRecord)
                .where(
                    IngestionJobRecord.run_id == run.id,
                    IngestionJobRecord.id != record.id,
                    IngestionJobRecord.status.in_([JobStatus.QUEUED.value, JobStatus.LEASED.value]),
                )
            )
            if unfinished == 0:
                state = _run_state(run).transition(
                    RunStatus.SUCCEEDED,
                    checkpoint="completed",
                    at=now,
                )
                _apply_run_state(run, state)

            session.add(
                _event(
                    run=run,
                    event_type="job.completed",
                    worker_id=worker_id,
                    payload={"job_id": str(job.id), "attempt": job.attempts},
                )
            )

    def fail(
        self,
        job: ClaimedJob,
        *,
        worker_id: str,
        error_code: str,
        error_detail: str,
        retryable: bool,
    ) -> None:
        now = datetime.now(UTC)
        safe_detail = error_detail[:1000]
        with self._session_factory.begin() as session:
            record, run = self._locked_job_and_run(session, job, worker_id)
            record.last_error_code = error_code[:80]
            record.last_error_detail = safe_detail
            record.lease_owner = None
            record.lease_expires_at = None
            record.updated_at = now

            should_retry = retryable and record.attempts < record.max_attempts
            if should_retry:
                retry_delay = min(2**record.attempts, 60)
                record.status = JobStatus.QUEUED.value
                record.available_at = now + timedelta(seconds=retry_delay)
                next_state = RunStatus.RETRY_WAIT
                event_type = "job.retry_scheduled"
            else:
                record.status = JobStatus.FAILED.value
                next_state = RunStatus.NEEDS_ATTENTION
                event_type = "job.failed"

            state = _run_state(run).transition(
                next_state,
                checkpoint=record.task_type,
                error_code=record.last_error_code,
                error_detail=safe_detail,
                at=now,
            )
            _apply_run_state(run, state)
            session.add(
                _event(
                    run=run,
                    event_type=event_type,
                    worker_id=worker_id,
                    payload={
                        "job_id": str(job.id),
                        "attempt": record.attempts,
                        "max_attempts": record.max_attempts,
                        "error_code": record.last_error_code,
                    },
                )
            )

    @staticmethod
    def _locked_job_and_run(
        session: Session,
        job: ClaimedJob,
        worker_id: str,
    ) -> tuple[IngestionJobRecord, IngestionRunRecord]:
        record = session.scalar(
            select(IngestionJobRecord).where(IngestionJobRecord.id == job.id).with_for_update()
        )
        if (
            record is None
            or record.status != JobStatus.LEASED.value
            or record.lease_owner != worker_id
        ):
            raise JobLeaseError(f"worker {worker_id} no longer owns job {job.id}")

        run = session.get(IngestionRunRecord, record.run_id, with_for_update=True)
        if run is None:
            raise RuntimeError(f"job {job.id} references a missing run")
        return record, run
