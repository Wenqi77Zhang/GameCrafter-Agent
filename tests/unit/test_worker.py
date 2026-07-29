from typing import Any
from uuid import uuid4

from gamecrafter.application.jobs import (
    ClaimedJob,
    RetryableJobError,
    TerminalJobError,
    Worker,
)


class RecordingQueue:
    def __init__(self, job: ClaimedJob | None) -> None:
        self.job = job
        self.completed = False
        self.failure: dict[str, Any] | None = None

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        return self.job

    def complete(self, job: ClaimedJob, *, worker_id: str) -> None:
        self.completed = True

    def fail(
        self,
        job: ClaimedJob,
        *,
        worker_id: str,
        error_code: str,
        error_detail: str,
        retryable: bool,
    ) -> None:
        self.failure = {
            "error_code": error_code,
            "error_detail": error_detail,
            "retryable": retryable,
        }


def make_job(task_type: str = "test.task") -> ClaimedJob:
    return ClaimedJob(
        id=uuid4(),
        run_id=uuid4(),
        task_type=task_type,
        payload={"value": 7},
        attempts=1,
        max_attempts=3,
    )


def make_worker(queue: RecordingQueue, handler: Any) -> Worker:
    return Worker(
        queue=queue,
        handlers={"test.task": handler},
        worker_id="test-worker",
        lease_seconds=30,
    )


def test_worker_completes_a_registered_handler() -> None:
    queue = RecordingQueue(make_job())
    received: list[ClaimedJob] = []
    worker = make_worker(queue, received.append)

    assert worker.run_once() is True
    assert received == [queue.job]
    assert queue.completed is True
    assert queue.failure is None


def test_worker_marks_unknown_tasks_as_terminal() -> None:
    queue = RecordingQueue(make_job("missing.task"))
    worker = make_worker(queue, lambda payload: None)

    worker.run_once()

    assert queue.failure == {
        "error_code": "unknown_task_type",
        "error_detail": "no handler registered for missing.task",
        "retryable": False,
    }


def test_worker_preserves_explicit_failure_policy() -> None:
    for error, expected_retryable in [
        (RetryableJobError("temporary"), True),
        (TerminalJobError("invalid input"), False),
    ]:
        queue = RecordingQueue(make_job())

        def fail(_: ClaimedJob, raised: Exception = error) -> None:
            raise raised

        make_worker(queue, fail).run_once()

        assert queue.failure is not None
        assert queue.failure["retryable"] is expected_retryable
