"""Self-diagnostics for the local database-backed runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.domain.runs.state import JobStatus
from gamecrafter.infrastructure.database.models import (
    RuntimeHeartbeatRecord,
    WorkflowJobRecord,
)


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DatabaseOperationsService:
    """Record worker liveness and expose safe aggregate queue diagnostics."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def heartbeat(self, worker_id: str) -> None:
        """Upsert one bounded worker heartbeat without retaining history indefinitely."""

        now = self._clock()
        component_key = f"worker:{worker_id}"
        with self._sessions.begin() as session:
            record = session.get(RuntimeHeartbeatRecord, component_key)
            if record is None:
                session.add(
                    RuntimeHeartbeatRecord(
                        component_key=component_key,
                        component_type="worker",
                        instance_id=worker_id,
                        started_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                record.last_seen_at = now

    def status(self, *, stale_after_seconds: int) -> dict[str, object]:
        """Return privacy-safe operational state and actionable queue aggregates."""

        now = self._clock()
        with self._sessions() as session:
            heartbeat = session.scalar(
                select(RuntimeHeartbeatRecord)
                .where(RuntimeHeartbeatRecord.component_type == "worker")
                .order_by(RuntimeHeartbeatRecord.last_seen_at.desc())
                .limit(1)
            )
            queue_counts = {
                status: count
                for status, count in session.execute(
                    select(WorkflowJobRecord.status, func.count())
                    .group_by(WorkflowJobRecord.status)
                    .order_by(WorkflowJobRecord.status)
                ).all()
            }
            oldest_queued_at = session.scalar(
                select(func.min(WorkflowJobRecord.created_at)).where(
                    WorkflowJobRecord.status == JobStatus.QUEUED.value
                )
            )
            expired_leases = session.scalar(
                select(func.count())
                .select_from(WorkflowJobRecord)
                .where(
                    WorkflowJobRecord.status == JobStatus.LEASED.value,
                    WorkflowJobRecord.lease_expires_at <= now,
                )
            )

        last_seen_at = _aware_utc(heartbeat.last_seen_at) if heartbeat else None
        heartbeat_age = max(0, int((now - last_seen_at).total_seconds())) if last_seen_at else None
        if heartbeat is None:
            worker_status = "missing"
        elif heartbeat_age is not None and heartbeat_age > stale_after_seconds:
            worker_status = "stale"
        else:
            worker_status = "healthy"

        oldest_age = (
            max(0, int((now - _aware_utc(oldest_queued_at)).total_seconds()))
            if oldest_queued_at
            else None
        )
        attention_codes: list[str] = []
        if worker_status == "missing":
            attention_codes.append("worker_missing")
        elif worker_status == "stale":
            attention_codes.append("worker_stale")
        if expired_leases:
            attention_codes.append("expired_job_leases")

        return {
            "status": "ready" if not attention_codes else "attention",
            "database": "connected",
            "worker": {
                "status": worker_status,
                "last_seen_at": last_seen_at,
                "age_seconds": heartbeat_age,
                "stale_after_seconds": stale_after_seconds,
            },
            "queue": {
                "queued": int(queue_counts.get(JobStatus.QUEUED.value, 0)),
                "leased": int(queue_counts.get(JobStatus.LEASED.value, 0)),
                "failed": int(queue_counts.get(JobStatus.FAILED.value, 0)),
                "oldest_queued_age_seconds": oldest_age,
                "expired_leases": int(expired_leases or 0),
            },
            "attention_codes": attention_codes,
            "observed_at": now,
        }
