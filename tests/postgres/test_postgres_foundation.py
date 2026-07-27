import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import Worker
from gamecrafter.domain.runs.state import RunStatus
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.models import IngestionRunRecord
from gamecrafter.infrastructure.database.run_service import DatabaseRunService

pytestmark = pytest.mark.postgres


def postgres_sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True), expire_on_commit=False
    )


def test_migration_enables_pgvector_and_worker_transactions() -> None:
    sessions = postgres_sessions()
    slug = f"nte-{uuid4().hex}"
    commands = DatabaseRunService(sessions)
    project_id = commands.create_project(slug=slug, name="异环")
    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key="postgres-foundation",
        task_type="test.postgres",
    )
    worker = Worker(
        queue=DatabaseJobQueue(sessions),
        handlers={"test.postgres": lambda payload: None},
        worker_id="postgres-test-worker",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with sessions() as session:
        extension_version = session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        run = session.scalar(select(IngestionRunRecord).where(IngestionRunRecord.id == run_id))

    assert extension_version is not None
    assert run is not None
    assert run.status == RunStatus.SUCCEEDED.value
