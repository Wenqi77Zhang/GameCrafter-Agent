from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.application.jobs import Worker
from gamecrafter.domain.runs.state import JobStatus, RunStatus
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    IngestionJobRecord,
    IngestionRunRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_project_run_and_job_complete_as_one_audited_flow() -> None:
    sessions = make_session_factory()
    commands = DatabaseRunService(sessions)
    project_id = commands.create_project(slug="nte", name="异环")
    assert commands.create_project(slug="nte", name="ignored duplicate") == project_id

    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key="source-batch-1",
        task_type="test.capture",
        payload={"source_count": 5},
    )
    assert (
        commands.enqueue_run(
            project_id=project_id,
            idempotency_key="source-batch-1",
            task_type="test.capture",
        )
        == run_id
    )

    handled: list[dict[str, object]] = []
    worker = Worker(
        queue=DatabaseJobQueue(sessions),
        handlers={"test.capture": lambda payload: handled.append(dict(payload))},
        worker_id="worker-1",
        lease_seconds=30,
    )

    assert worker.run_once() is True
    assert worker.run_once() is False
    assert handled == [{"source_count": 5}]

    with sessions() as session:
        run = session.get(IngestionRunRecord, run_id)
        job = session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.run_id == run_id))
        event_types = session.scalars(
            select(AuditEventRecord.event_type)
            .where(AuditEventRecord.run_id == run_id)
            .order_by(AuditEventRecord.occurred_at)
        ).all()

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED.value
    assert run.checkpoint == "completed"
    assert run.started_at is not None
    assert run.finished_at is not None
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value
    assert event_types == ["run.queued", "job.leased", "job.completed"]


def test_unknown_job_becomes_visible_instead_of_looping_forever() -> None:
    sessions = make_session_factory()
    commands = DatabaseRunService(sessions)
    project_id = commands.create_project(slug="nte", name="异环")
    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key="unknown-task",
        task_type="missing.task",
    )
    worker = Worker(
        queue=DatabaseJobQueue(sessions),
        handlers={},
        worker_id="worker-1",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with sessions() as session:
        run = session.get(IngestionRunRecord, run_id)
        job = session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.run_id == run_id))

    assert run is not None
    assert run.status == RunStatus.NEEDS_ATTENTION.value
    assert run.last_error_code == "unknown_task_type"
    assert job is not None
    assert job.status == JobStatus.FAILED.value


def test_expired_final_lease_becomes_visible_for_human_recovery() -> None:
    sessions = make_session_factory()
    commands = DatabaseRunService(sessions)
    project_id = commands.create_project(slug="nte", name="异环")
    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key="worker-crashed",
        task_type="test.capture",
        max_attempts=1,
    )
    with sessions.begin() as session:
        run = session.get(IngestionRunRecord, run_id)
        job = session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.run_id == run_id))
        assert run is not None
        assert job is not None
        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(UTC) - timedelta(minutes=2)
        job.status = JobStatus.LEASED.value
        job.attempts = 1
        job.lease_owner = "crashed-worker"
        job.lease_expires_at = datetime.now(UTC) - timedelta(minutes=1)

    claimed = DatabaseJobQueue(sessions).claim_next(
        worker_id="recovery-worker",
        lease_seconds=30,
    )

    assert claimed is None
    with sessions() as session:
        run = session.get(IngestionRunRecord, run_id)
        job = session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.run_id == run_id))
    assert run is not None
    assert run.status == RunStatus.NEEDS_ATTENTION.value
    assert run.last_error_code == "lease_expired"
    assert job is not None
    assert job.status == JobStatus.FAILED.value
