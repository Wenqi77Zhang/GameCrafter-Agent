from datetime import UTC, datetime

import pytest

from gamecrafter.domain.runs.state import RunStatus, RunTransitionError, WorkflowRun


def test_run_follows_a_valid_success_path() -> None:
    started_at = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
    finished_at = datetime(2026, 7, 28, 8, 1, tzinfo=UTC)

    running = WorkflowRun().transition(
        RunStatus.RUNNING,
        checkpoint="policy_check",
        at=started_at,
    )
    succeeded = running.transition(
        RunStatus.SUCCEEDED,
        checkpoint="completed",
        at=finished_at,
    )

    assert running.started_at == started_at
    assert succeeded.status is RunStatus.SUCCEEDED
    assert succeeded.finished_at == finished_at
    assert succeeded.version == 3


def test_terminal_run_cannot_be_silently_reopened() -> None:
    succeeded = WorkflowRun().transition(RunStatus.RUNNING).transition(RunStatus.SUCCEEDED)

    with pytest.raises(RunTransitionError, match="cannot transition"):
        succeeded.transition(RunStatus.RUNNING)


def test_retry_requires_an_explicit_wait_checkpoint() -> None:
    retry_wait = (
        WorkflowRun()
        .transition(RunStatus.RUNNING, checkpoint="capture")
        .transition(
            RunStatus.RETRY_WAIT,
            error_code="timeout",
            error_detail="official source timed out",
        )
    )

    queued = retry_wait.transition(RunStatus.QUEUED)

    assert queued.status is RunStatus.QUEUED
    assert queued.last_error_code is None
    assert queued.last_error_detail is None
