"""Real PostgreSQL acceptance for the zero-cost NTE Knowledge path."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import Worker
from gamecrafter.application.knowledge_jobs import (
    EXTRACT_KNOWLEDGE_TASK,
    KnowledgeExtractionHandlers,
)
from gamecrafter.application.ports.model_gateway import ClaimExtractionRequest
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.knowledge_repository import (
    DatabaseKnowledgeRepository,
)
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    KnowledgeExtractionResultRecord,
    ModelInvocationRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
    WorkflowJobRecord,
    WorkflowRunRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.workspace_service import DatabaseWorkspaceService
from gamecrafter.infrastructure.models.gateways import ReplayModelGateway
from gamecrafter.infrastructure.models.replay_fixtures import load_replay_fixture
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

pytestmark = pytest.mark.postgres

FIXTURE_PATH = Path("fixtures/nte/official-homepage-en-v1.json")


def _postgres_sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    database_name = parsed.database or ""
    if "test" not in database_name.lower() and "acceptance" not in database_name.lower():
        pytest.fail("NTE acceptance requires a disposable test or acceptance database")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True),
        expire_on_commit=False,
    )


def _seed_acceptance_target(
    sessions: sessionmaker[Session],
    storage: LocalObjectStorage,
) -> tuple[UUID, UUID, UUID, str, ReplayModelGateway]:
    """Bind the reviewed NTE fixture to a unique immutable PostgreSQL version."""

    loaded = load_replay_fixture(FIXTURE_PATH)
    source_version_id = uuid4()
    stored = storage.put(
        BytesIO(loaded.request.text.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
    )
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"nte-c25-{uuid4().hex}",
        name="异环 C2.5 acceptance",
    )
    entity, created = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE: Neverness to Everness"],
        actor_id="c25-acceptance",
    )
    assert created is True
    entity_id = UUID(str(entity["id"]))
    rebound_request = ClaimExtractionRequest(
        source_version_id=source_version_id,
        subject_entity_key=str(entity["canonical_key"]),
        text=loaded.request.text,
        text_start_offset=loaded.request.text_start_offset,
        locale=loaded.request.locale,
        region=loaded.request.region,
        prompt_version=loaded.request.prompt_version,
        schema_version=loaded.request.schema_version,
    )
    fixture = next(iter(loaded.fixtures.values()))
    gateway = ReplayModelGateway({rebound_request.fingerprint_sha256: fixture})

    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=loaded.source_url,
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        stored_record = session.scalar(
            select(StoredObjectRecord).where(StoredObjectRecord.object_key == stored.key)
        )
        if stored_record is None:
            stored_record = StoredObjectRecord(
                object_key=stored.key,
                sha256=stored.digest.value,
                size_bytes=stored.size_bytes,
                media_type=stored.media_type,
            )
            session.add(stored_record)
        else:
            assert stored_record.sha256 == stored.digest.value
            assert stored_record.size_bytes == stored.size_bytes
            assert stored_record.media_type == stored.media_type
        session.add(source)
        session.flush()
        version = SourceVersionRecord(
            id=source_version_id,
            source_id=source.id,
            version_number=1,
            title="NTE official homepage acceptance snapshot",
            capture_method="http",
            change_kind="initial",
            raw_content_sha256=stored.digest.value,
            normalized_text_sha256=stored.digest.value,
            evidence_fingerprint_sha256=stored.digest.value,
            parser_version="c25-acceptance-v1",
            capture_policy_version="c25-reviewed-public-fixture-v1",
            fetched_at=loaded.captured_at,
            details={"acceptance_fixture": True, "live_capture": False},
        )
        session.add(version)
        session.flush()
        session.add(
            SourceAssetRecord(
                source_version_id=version.id,
                stored_object_id=stored_record.id,
                role="normalized_text",
                ordinal=0,
            )
        )
    return project_id, entity_id, source_version_id, loaded.request.text, gateway


def test_nte_fixture_reaches_reviewable_claims_through_real_postgresql(
    tmp_path: Path,
) -> None:
    sessions = _postgres_sessions()
    storage = LocalObjectStorage(tmp_path / "objects")
    project_id, entity_id, source_version_id, source_text, gateway = _seed_acceptance_target(
        sessions,
        storage,
    )
    command = DatabaseWorkspaceService(sessions)
    payload = {
        "source_version_id": str(source_version_id),
        "subject_entity_id": str(entity_id),
    }
    run, created = command.enqueue(
        project_id=project_id,
        idempotency_key="c25-nte-exact-replay",
        task_type=EXTRACT_KNOWLEDGE_TASK,
        payload=payload,
        actor_id="c25-acceptance",
    )
    assert created is True
    replayed, duplicate_created = command.enqueue(
        project_id=project_id,
        idempotency_key="c25-nte-exact-replay",
        task_type=EXTRACT_KNOWLEDGE_TASK,
        payload=payload,
        actor_id="c25-acceptance",
    )
    assert duplicate_created is False
    assert replayed["id"] == run["id"]
    run_id = UUID(str(run["id"]))

    repository = DatabaseKnowledgeRepository(sessions, actor_id="c25-acceptance-worker")
    worker = Worker(
        queue=DatabaseJobQueue(sessions),
        handlers={
            EXTRACT_KNOWLEDGE_TASK: KnowledgeExtractionHandlers(
                repository=repository,
                object_storage=storage,
                gateway=gateway,
                document_max_bytes=2 * 1024 * 1024,
            ).extract
        },
        worker_id="c25-acceptance-worker",
        lease_seconds=30,
    )
    assert worker.run_once() is True

    with sessions() as session:
        persisted_run = session.get(WorkflowRunRecord, run_id)
        result = session.get(KnowledgeExtractionResultRecord, run_id)
        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.run_id == run_id)
        )
        event_types = set(
            session.scalars(
                select(AuditEventRecord.event_type).where(AuditEventRecord.run_id == run_id)
            )
        )
        assert persisted_run is not None and persisted_run.status == "succeeded"
        assert persisted_run.workflow_kind == EXTRACT_KNOWLEDGE_TASK
        assert result is not None and result.claim_count == 2
        assert result.invocation_count == 1
        assert result.total_tokens == 0
        assert invocation is not None and invocation.provider == "replay"
        assert invocation.input_tokens == invocation.output_tokens == invocation.total_tokens == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(WorkflowJobRecord)
                .where(WorkflowJobRecord.run_id == run_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(KnowledgeClaimRecord)
                .where(KnowledgeClaimRecord.extraction_run_id == run_id)
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ClaimEvidenceSpanRecord)
                .join(KnowledgeClaimRecord)
                .where(KnowledgeClaimRecord.extraction_run_id == run_id)
            )
            == 2
        )
        assert {"knowledge.extraction_persisted", "job.completed"} <= event_types

    claims = repository.list_claims(
        project_id,
        subject_entity_id=entity_id,
        extraction_run_id=run_id,
    )
    assert {claim["predicate"] for claim in claims} == {"game.developer", "genre.primary"}
    for claim in claims:
        assert claim["status"] == "candidate_unreviewed"
        for evidence in claim["evidence"]:
            assert evidence["quote"] in source_text
            assert evidence["source_version_id"] == str(source_version_id)
            assert evidence["source_url"] == "https://nte.perfectworld.com/en/main.html"

    read_model = repository.extraction_result(project_id=project_id, run_id=run_id)
    assert read_model["claim_count"] == 2
    assert read_model["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert "text" not in read_model
    assert "object_key" not in read_model
