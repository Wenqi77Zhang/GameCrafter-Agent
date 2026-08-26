from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.domain.runs.state import JobStatus
from gamecrafter.infrastructure.database.models import (
    Base,
    RuntimeHeartbeatRecord,
    WorkflowJobRecord,
)
from gamecrafter.infrastructure.database.operations_service import DatabaseOperationsService
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_operations_exposes_missing_worker_instead_of_fake_readiness() -> None:
    sessions = make_session_factory()
    status = DatabaseOperationsService(sessions).status(stale_after_seconds=300)

    assert status["status"] == "attention"
    assert status["worker"]["status"] == "missing"
    assert status["attention_codes"] == ["worker_missing"]
    assert status["queue"] == {
        "queued": 0,
        "leased": 0,
        "failed": 0,
        "oldest_queued_age_seconds": None,
        "expired_leases": 0,
    }


def test_operations_detects_stale_worker_and_expired_lease() -> None:
    sessions = make_session_factory()
    now = [datetime(2026, 8, 27, 0, 0, tzinfo=UTC)]
    operations = DatabaseOperationsService(sessions, clock=lambda: now[0])
    operations.heartbeat("worker-1")
    project_id = DatabaseRunService(sessions).create_project(slug="nte-ops", name="异环")
    run_id = DatabaseRunService(sessions).enqueue_run(
        project_id=project_id,
        idempotency_key="ops-expired",
        task_type="test.capture",
    )
    with sessions.begin() as session:
        job = session.scalar(select(WorkflowJobRecord).where(WorkflowJobRecord.run_id == run_id))
        assert job is not None
        job.status = JobStatus.LEASED.value
        job.lease_owner = "worker-1"
        job.lease_expires_at = now[0] - timedelta(seconds=1)

    now[0] += timedelta(seconds=301)
    status = operations.status(stale_after_seconds=300)

    assert status["status"] == "attention"
    assert status["worker"]["status"] == "stale"
    assert status["worker"]["age_seconds"] == 301
    assert status["queue"]["leased"] == 1
    assert status["queue"]["expired_leases"] == 1
    assert status["attention_codes"] == ["worker_stale", "expired_job_leases"]
    with sessions() as session:
        heartbeat = session.get(RuntimeHeartbeatRecord, "worker:worker-1")
    assert heartbeat is not None
    assert heartbeat.instance_id == "worker-1"
