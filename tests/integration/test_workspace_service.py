from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.infrastructure.database.models import (
    Base,
    DiscoveryCandidateRecord,
    IngestionJobRecord,
)
from gamecrafter.infrastructure.database.workspace_service import (
    DatabaseWorkspaceService,
    WorkspaceConflictError,
)


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_project_and_discovery_run_are_idempotent_but_not_ambiguous() -> None:
    sessions = make_session_factory()
    workspace = DatabaseWorkspaceService(sessions)
    project, created = workspace.create_project(
        slug="nte",
        name="异环",
        default_locale="zh-CN",
        actor_id="test-user",
    )
    assert created is True
    repeated, created = workspace.create_project(
        slug="nte",
        name="ignored",
        default_locale="en",
        actor_id="test-user",
    )
    assert created is False
    assert repeated["id"] == project["id"]

    payload = {
        "mode": "quick",
        "listing_urls": ["https://nte.perfectworld.com/en/article/news/index.html"],
        "candidate_limit": 30,
        "source_types": [],
    }
    run, created = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="discovery-0001",
        task_type="source.discover",
        payload=payload,
        actor_id="test-user",
    )
    assert created is True
    repeated, created = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="discovery-0001",
        task_type="source.discover",
        payload=payload,
        actor_id="test-user",
    )
    assert created is False
    assert repeated["id"] == run["id"]
    with pytest.raises(WorkspaceConflictError, match="different request"):
        workspace.enqueue(
            project_id=UUID(project["id"]),
            idempotency_key="discovery-0001",
            task_type="source.capture",
            payload={"url": "https://nte.perfectworld.com/en/"},
            actor_id="test-user",
        )


def test_candidate_selection_is_atomic_and_project_scoped() -> None:
    sessions = make_session_factory()
    workspace = DatabaseWorkspaceService(sessions)
    project, _ = workspace.create_project(
        slug="nte",
        name="异环",
        default_locale="zh-CN",
        actor_id="test-user",
    )
    discovery, _ = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="discovery-0002",
        task_type="source.discover",
        payload={
            "mode": "quick",
            "listing_urls": ["https://nte.perfectworld.com/en/article/news/index.html"],
        },
        actor_id="test-user",
    )
    candidate_id = uuid4()
    with sessions.begin() as session:
        session.add(
            DiscoveryCandidateRecord(
                id=candidate_id,
                run_id=UUID(discovery["id"]),
                project_id=UUID(project["id"]),
                canonical_url="https://nte.perfectworld.com/en/article/news/launch.html",
                site_key="nte-global",
                locale="en",
                region="global",
                title="Launch",
                published_at=datetime.now(UTC),
                source_type="news",
                classification_basis="official listing metadata",
                status="discovered",
            )
        )

    capture, created = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="capture-0001",
        task_type="source.capture",
        payload={"candidate_id": str(candidate_id)},
        candidate_id=candidate_id,
        actor_id="test-user",
    )
    assert created is True
    with sessions() as session:
        candidate = session.get(DiscoveryCandidateRecord, candidate_id)
        job = session.scalar(
            select(IngestionJobRecord).where(IngestionJobRecord.run_id == UUID(capture["id"]))
        )
    assert candidate is not None
    assert candidate.status == "selected"
    assert candidate.selected_at is not None
    assert job is not None
    assert job.payload == {"candidate_id": str(candidate_id)}

    with pytest.raises(WorkspaceConflictError, match="no longer available"):
        workspace.enqueue(
            project_id=UUID(project["id"]),
            idempotency_key="capture-0002",
            task_type="source.capture",
            payload={"candidate_id": str(candidate_id)},
            candidate_id=candidate_id,
            actor_id="test-user",
        )


def test_run_events_reject_foreign_cursor() -> None:
    sessions = make_session_factory()
    workspace = DatabaseWorkspaceService(sessions)
    project, _ = workspace.create_project(
        slug="nte",
        name="异环",
        default_locale="zh-CN",
        actor_id="test-user",
    )
    first, _ = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="run-events-1",
        task_type="source.capture",
        payload={"url": "https://nte.perfectworld.com/en/"},
        actor_id="test-user",
    )
    second, _ = workspace.enqueue(
        project_id=UUID(project["id"]),
        idempotency_key="run-events-2",
        task_type="source.capture",
        payload={"url": "https://nte.perfectworld.com/jp/"},
        actor_id="test-user",
    )
    first_events, terminal = workspace.events_after(UUID(first["id"]), None)
    assert terminal is False
    assert [item["event_type"] for item in first_events] == ["run.queued"]
    second_events, _ = workspace.events_after(UUID(second["id"]), None)
    with pytest.raises(WorkspaceConflictError, match="does not belong"):
        workspace.events_after(
            UUID(first["id"]),
            UUID(second_events[0]["id"]),
        )
