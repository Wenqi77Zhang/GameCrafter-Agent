from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import ClaimedJob, Worker
from gamecrafter.application.knowledge_jobs import (
    EXTRACT_KNOWLEDGE_TASK,
    KnowledgeExtractionHandlers,
)
from gamecrafter.domain.knowledge.claims import EntityType
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.knowledge_repository import (
    DatabaseKnowledgeRepository,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRecord,
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
from gamecrafter.infrastructure.models.gateways import ReplayModelGateway
from gamecrafter.infrastructure.models.replay_fixtures import load_replay_fixture
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

FIXTURE_PATH = Path("fixtures/nte/official-homepage-en-v1.json")
SOURCE_VERSION_ID = UUID("00000000-0000-0000-0000-00000000c222")


def _sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_target(
    factory: sessionmaker[Session], storage: LocalObjectStorage
) -> tuple[UUID, UUID, str]:
    loaded = load_replay_fixture(FIXTURE_PATH)
    text = loaded.document.normalized_text
    stored = storage.put(BytesIO(text.encode("utf-8")), media_type="text/plain; charset=utf-8")
    commands = DatabaseRunService(factory)
    project_id = commands.create_project(slug=f"nte-{uuid4().hex}", name="异环")
    with factory.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=loaded.source_url,
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        session.add(source)
        session.flush()
        version = SourceVersionRecord(
            id=SOURCE_VERSION_ID,
            source_id=source.id,
            version_number=1,
            title="Neverness to Everness",
            capture_method="http",
            change_kind="initial",
            raw_content_sha256=stored.digest.value,
            normalized_text_sha256=stored.digest.value,
            evidence_fingerprint_sha256=stored.digest.value,
            parser_version="test-v1",
            capture_policy_version="test-v1",
        )
        object_record = StoredObjectRecord(
            object_key=stored.key,
            sha256=stored.digest.value,
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
        )
        entity = KnowledgeEntityRecord(
            project_id=project_id,
            entity_type=EntityType.GAME.value,
            canonical_key="game:nte",
            display_name="异环",
            aliases=["NTE", "Neverness to Everness"],
        )
        session.add_all([version, object_record, entity])
        session.flush()
        session.add(
            SourceAssetRecord(
                source_version_id=version.id,
                stored_object_id=object_record.id,
                role="normalized_text",
                ordinal=0,
            )
        )
        entity_id = entity.id
    return project_id, entity_id, text


def test_worker_persists_atomic_evidence_result_trace_and_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    factory = _sessions()
    storage = LocalObjectStorage(tmp_path / "objects")
    project_id, entity_id, text = _seed_target(factory, storage)
    run_id = DatabaseRunService(factory).enqueue_run(
        project_id=project_id,
        idempotency_key="knowledge-extract-v1",
        task_type=EXTRACT_KNOWLEDGE_TASK,
        payload={
            "source_version_id": str(SOURCE_VERSION_ID),
            "subject_entity_id": str(entity_id),
        },
    )
    loaded = load_replay_fixture(FIXTURE_PATH)
    repository = DatabaseKnowledgeRepository(factory)
    handler = KnowledgeExtractionHandlers(
        repository=repository,
        object_storage=storage,
        gateway=ReplayModelGateway(loaded.fixtures),
        document_max_bytes=1024 * 1024,
    )
    worker = Worker(
        queue=DatabaseJobQueue(factory),
        handlers={EXTRACT_KNOWLEDGE_TASK: handler.extract},
        worker_id="test-knowledge-worker",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with factory() as session:
        run = session.get(WorkflowRunRecord, run_id)
        assert run is not None and run.status == "succeeded"
        result = session.get(KnowledgeExtractionResultRecord, run_id)
        assert result is not None
        assert result.claim_count == 2
        assert result.invocation_count == 1
        assert session.scalar(select(func.count()).select_from(KnowledgeClaimRecord)) == 2
        assert session.scalar(select(func.count()).select_from(ClaimEvidenceSpanRecord)) == 2
        invocation = session.scalar(select(ModelInvocationRecord))
        assert invocation is not None and invocation.status == "succeeded"
        assert invocation.provider == "replay"
        event_types = set(session.scalars(select(AuditEventRecord.event_type)))
        assert {"knowledge.extraction_persisted", "job.completed"} <= event_types

    job_id = factory().scalar(
        select(WorkflowJobRecord.id).where(WorkflowJobRecord.run_id == run_id)
    )
    assert job_id is not None
    handler.extract(
        ClaimedJob(
            id=job_id,
            run_id=run_id,
            task_type=EXTRACT_KNOWLEDGE_TASK,
            payload={
                "source_version_id": str(SOURCE_VERSION_ID),
                "subject_entity_id": str(entity_id),
            },
            attempts=2,
            max_attempts=3,
        )
    )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeClaimRecord)) == 2
        assert session.scalar(select(func.count()).select_from(ModelInvocationRecord)) == 1
    claims = repository.list_claims(project_id)
    assert claims[0]["evidence"][0]["quote"] in text
    read_model = repository.extraction_result(project_id=project_id, run_id=run_id)
    assert "text" not in read_model
    assert read_model["manifest_sha256"] == result.manifest_sha256


def test_missing_exact_replay_is_terminal_and_persists_redacted_failure(tmp_path: Path) -> None:
    factory = _sessions()
    storage = LocalObjectStorage(tmp_path / "objects")
    project_id, entity_id, _ = _seed_target(factory, storage)
    run_id = DatabaseRunService(factory).enqueue_run(
        project_id=project_id,
        idempotency_key="knowledge-no-replay",
        task_type=EXTRACT_KNOWLEDGE_TASK,
        payload={
            "source_version_id": str(SOURCE_VERSION_ID),
            "subject_entity_id": str(entity_id),
        },
    )
    handler = KnowledgeExtractionHandlers(
        repository=DatabaseKnowledgeRepository(factory),
        object_storage=storage,
        gateway=ReplayModelGateway({}),
        document_max_bytes=1024 * 1024,
    )
    worker = Worker(
        queue=DatabaseJobQueue(factory),
        handlers={EXTRACT_KNOWLEDGE_TASK: handler.extract},
        worker_id="test-knowledge-worker",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with factory() as session:
        run = session.get(WorkflowRunRecord, run_id)
        assert run is not None and run.status == "needs_attention"
        invocation = session.scalar(select(ModelInvocationRecord))
        assert invocation is not None and invocation.status == "failed"
        assert invocation.error_code == "ReplayFixtureNotFoundError"
        assert invocation.provider is None and invocation.response_id is None
        assert session.get(KnowledgeExtractionResultRecord, run_id) is None
        assert session.scalar(select(func.count()).select_from(KnowledgeClaimRecord)) == 0


def test_tampered_normalized_object_stops_before_model_invocation(tmp_path: Path) -> None:
    factory = _sessions()
    object_root = tmp_path / "objects"
    storage = LocalObjectStorage(object_root)
    project_id, entity_id, text = _seed_target(factory, storage)
    digest = sha256(text.encode("utf-8")).hexdigest()
    stored_path = object_root / "sha256" / digest[:2] / digest
    stored_path.write_bytes(b"tampered evidence bytes")
    run_id = DatabaseRunService(factory).enqueue_run(
        project_id=project_id,
        idempotency_key="knowledge-tampered-object",
        task_type=EXTRACT_KNOWLEDGE_TASK,
        payload={
            "source_version_id": str(SOURCE_VERSION_ID),
            "subject_entity_id": str(entity_id),
        },
    )
    loaded = load_replay_fixture(FIXTURE_PATH)
    handler = KnowledgeExtractionHandlers(
        repository=DatabaseKnowledgeRepository(factory),
        object_storage=storage,
        gateway=ReplayModelGateway(loaded.fixtures),
        document_max_bytes=1024 * 1024,
    )
    worker = Worker(
        queue=DatabaseJobQueue(factory),
        handlers={EXTRACT_KNOWLEDGE_TASK: handler.extract},
        worker_id="test-knowledge-worker",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with factory() as session:
        run = session.get(WorkflowRunRecord, run_id)
        assert run is not None and run.status == "needs_attention"
        assert "ObjectIntegrityError" in (run.last_error_detail or "")
        assert session.scalar(select(func.count()).select_from(ModelInvocationRecord)) == 0
        assert session.scalar(select(func.count()).select_from(KnowledgeClaimRecord)) == 0
        assert session.get(KnowledgeExtractionResultRecord, run_id) is None
