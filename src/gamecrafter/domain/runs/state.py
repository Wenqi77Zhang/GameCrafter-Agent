"""Pure workflow-run and job state rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum


class RunStatus(StrEnum):
    """Durable lifecycle shared by every bounded workflow run."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    NEEDS_ATTENTION = "needs_attention"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    """Durable lifecycle of a worker job."""

    QUEUED = "queued"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunTransitionError(ValueError):
    """Raised when a command attempts an invalid state transition."""


ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.RETRY_WAIT,
            RunStatus.NEEDS_ATTENTION,
            RunStatus.SUCCEEDED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RETRY_WAIT: frozenset(
        {RunStatus.QUEUED, RunStatus.NEEDS_ATTENTION, RunStatus.CANCELLED}
    ),
    RunStatus.NEEDS_ATTENTION: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """Framework-independent run state used by application services."""

    status: RunStatus = RunStatus.QUEUED
    checkpoint: str = "created"
    version: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error_code: str | None = None
    last_error_detail: str | None = None

    def transition(
        self,
        target: RunStatus,
        *,
        checkpoint: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        at: datetime | None = None,
    ) -> WorkflowRun:
        """Return a new validated state without mutating the current run."""

        if target not in ALLOWED_RUN_TRANSITIONS[self.status]:
            raise RunTransitionError(f"cannot transition run from {self.status} to {target}")

        changed_at = at or datetime.now(UTC)
        started_at = self.started_at
        finished_at = self.finished_at
        if target is RunStatus.RUNNING and started_at is None:
            started_at = changed_at
        if target in {RunStatus.SUCCEEDED, RunStatus.CANCELLED}:
            finished_at = changed_at

        return replace(
            self,
            status=target,
            checkpoint=checkpoint or self.checkpoint,
            version=self.version + 1,
            started_at=started_at,
            finished_at=finished_at,
            last_error_code=error_code,
            last_error_detail=error_detail,
        )
