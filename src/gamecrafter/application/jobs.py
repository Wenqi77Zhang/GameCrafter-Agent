"""Application contracts for durable background work."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from gamecrafter.security.redaction import redact_error_detail


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A leased job safe for one worker to execute."""

    id: UUID
    run_id: UUID
    task_type: str
    payload: Mapping[str, Any]
    attempts: int
    max_attempts: int


class JobQueue(Protocol):
    """Persistence port used by the worker runtime."""

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        """Lease the next available job, if any."""

    def complete(self, job: ClaimedJob, *, worker_id: str) -> None:
        """Commit a successful job and its run state."""

    def fail(
        self,
        job: ClaimedJob,
        *,
        worker_id: str,
        error_code: str,
        error_detail: str,
        retryable: bool,
    ) -> None:
        """Record a failure and either retry or expose it for attention."""


JobHandler = Callable[[Mapping[str, Any]], None]


class JobExecutionError(RuntimeError):
    """Base error with an explicit retry policy."""

    retryable = False


class RetryableJobError(JobExecutionError):
    """Transient failure that may consume another bounded attempt."""

    retryable = True


class TerminalJobError(JobExecutionError):
    """Permanent failure that must become visible to a human."""


class Worker:
    """Small deterministic worker runtime around a durable queue."""

    def __init__(
        self,
        *,
        queue: JobQueue,
        handlers: Mapping[str, JobHandler],
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self._queue = queue
        self._handlers = handlers
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    def run_once(self) -> bool:
        """Execute at most one job and report whether work was claimed."""

        job = self._queue.claim_next(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        if job is None:
            return False

        try:
            handler = self._handlers[job.task_type]
            handler(job.payload)
        except KeyError:
            self._queue.fail(
                job,
                worker_id=self._worker_id,
                error_code="unknown_task_type",
                error_detail=f"no handler registered for {job.task_type}",
                retryable=False,
            )
        except JobExecutionError as error:
            self._queue.fail(
                job,
                worker_id=self._worker_id,
                error_code=type(error).__name__,
                error_detail=redact_error_detail(str(error)),
                retryable=error.retryable,
            )
        except Exception as error:  # noqa: BLE001 - worker boundary must persist unknown failures
            self._queue.fail(
                job,
                worker_id=self._worker_id,
                error_code=type(error).__name__,
                error_detail=redact_error_detail(str(error)),
                retryable=True,
            )
        else:
            self._queue.complete(job, worker_id=self._worker_id)
        return True
