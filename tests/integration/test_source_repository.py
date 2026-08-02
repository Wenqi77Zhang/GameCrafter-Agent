from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import Worker
from gamecrafter.application.ports.object_storage import StoredObject
from gamecrafter.application.ports.site_adapter import AdaptedSource
from gamecrafter.application.ports.source_capture import CapturedPage
from gamecrafter.application.ports.source_repository import PreparedCapture, PreparedImage
from gamecrafter.application.source_ingestion import CaptureRuntime, SourceIngestionHandlers
from gamecrafter.domain.knowledge.sources import CaptureMethod, EvidenceDigest, SourceType
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    DiscoveryCandidateRecord,
    SourceAssetRecord,
    SourceVersionRecord,
    WorkflowRunRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.source_repository import (
    DatabaseSourceRepository,
    SourcePersistenceError,
)
from gamecrafter.infrastructure.ingestion.html import extract_evidence_document
from gamecrafter.infrastructure.ingestion.nte import NteSiteAdapter
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def stored(body: bytes, media_type: str) -> StoredObject:
    digest = sha256(body).hexdigest()
    return StoredObject(
        key=f"sha256/{digest[:2]}/{digest}",
        digest=EvidenceDigest(digest),
        size_bytes=len(body),
        media_type=media_type,
    )


def prepared(
    text: bytes,
    *,
    etag: str,
    images: tuple[PreparedImage, ...] = (),
) -> PreparedCapture:
    raw = b"<main>" + text + b"</main>"
    normalized = stored(text, "text/plain; charset=utf-8")
    image_fingerprints = "\0".join(image.stored_object.digest.value for image in images)
    return PreparedCapture(
        source=AdaptedSource(
            canonical_url=(
                "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
            ),
            site_key="nte-global",
            locale="en",
            region="global",
            source_type=SourceType.UPDATE,
            raw_category="gamenews",
            classification_basis="title rule",
        ),
        title="Version update",
        published_at=None,
        fetched_at=datetime.now(UTC),
        capture_method=CaptureMethod.HTTP,
        http_status=200,
        etag=etag,
        last_modified=None,
        raw_object=stored(raw, "text/html"),
        normalized_object=normalized,
        images=images,
        image_candidate_count=len(images),
        image_failure_count=0,
        evidence_fingerprint_sha256=sha256(
            f"parser\0{normalized.digest.value}\0{image_fingerprints}".encode()
        ).hexdigest(),
        parser_version="parser-v1",
        capture_policy_version="policy-v1",
        document_language="en",
    )


def test_repository_reuses_identical_capture_and_versions_meaningful_change() -> None:
    factory = sessions()
    commands = DatabaseRunService(factory)
    project_id = commands.create_project(slug=f"nte-{uuid4().hex}", name="异环")
    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key=f"capture-{uuid4().hex}",
        task_type="source.capture",
    )
    repository = DatabaseSourceRepository(factory)

    official_image = PreparedImage(
        original_url="https://nte.perfectworld.com/images/update.png",
        alt_text="Official update",
        stored_object=stored(b"\x89PNG\r\n\x1a\nimage", "image/png"),
    )
    first = repository.persist_capture(
        run_id=run_id,
        candidate_id=None,
        capture=prepared(b"first evidence", etag='"v1"', images=(official_image,)),
    )
    duplicate = repository.persist_capture(
        run_id=run_id,
        candidate_id=None,
        capture=prepared(
            b"first evidence",
            etag='"v1-again"',
            images=(official_image,),
        ),
    )
    changed = repository.persist_capture(
        run_id=run_id,
        candidate_id=None,
        capture=prepared(b"meaningfully changed evidence", etag='"v2"'),
    )

    assert first.created_version is True
    assert duplicate.source_version_id == first.source_version_id
    assert duplicate.created_version is False
    assert changed.version_number == 2
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceVersionRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SourceAssetRecord)) == 5
        event_types = set(session.scalars(select(AuditEventRecord.event_type)))
        assert "source.version_captured" in event_types
        assert "source.capture_unchanged" in event_types


def test_selected_candidate_can_cross_runs_inside_one_project() -> None:
    factory = sessions()
    commands = DatabaseRunService(factory)
    project_id = commands.create_project(slug=f"nte-{uuid4().hex}", name="异环")
    discovery_run = commands.enqueue_run(
        project_id=project_id,
        idempotency_key=f"discover-{uuid4().hex}",
        task_type="source.discover",
    )
    capture_run = commands.enqueue_run(
        project_id=project_id,
        idempotency_key=f"capture-{uuid4().hex}",
        task_type="source.capture",
    )
    candidate_id = uuid4()
    candidate_url = "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
    with factory.begin() as session:
        session.add(
            DiscoveryCandidateRecord(
                id=candidate_id,
                run_id=discovery_run,
                project_id=project_id,
                canonical_url=candidate_url,
                site_key="nte-global",
                locale="en",
                region="global",
                title="Version update",
                source_type="update",
                raw_category="gamenews",
                classification_basis="title rule",
                status="selected",
            )
        )
    repository = DatabaseSourceRepository(factory)

    selected = repository.selected_candidate(
        run_id=capture_run,
        candidate_id=candidate_id,
    )
    result = repository.persist_capture(
        run_id=capture_run,
        candidate_id=candidate_id,
        capture=prepared(b"selected evidence", etag='"selected"'),
    )

    assert selected.canonical_url == candidate_url
    with factory() as session:
        candidate = session.get(DiscoveryCandidateRecord, candidate_id)
        assert candidate is not None
        assert candidate.status == "imported"
        assert candidate.imported_source_id == result.source_id

    other_project_id = commands.create_project(
        slug=f"other-{uuid4().hex}",
        name="Other",
    )
    other_run = commands.enqueue_run(
        project_id=other_project_id,
        idempotency_key=f"capture-{uuid4().hex}",
        task_type="source.capture",
    )
    with pytest.raises(SourcePersistenceError, match="this project"):
        repository.selected_candidate(run_id=other_run, candidate_id=candidate_id)


class StaticFetcher:
    def __init__(self, captured: CapturedPage) -> None:
        self.captured = captured

    def fetch(self, request):
        return self.captured


class AllowingRobots:
    def ensure_allowed(self, url: str) -> object:
        return object()


def test_worker_executes_direct_capture_to_audited_immutable_version(tmp_path: Path) -> None:
    factory = sessions()
    commands = DatabaseRunService(factory)
    project_id = commands.create_project(slug=f"nte-{uuid4().hex}", name="异环")
    url = "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
    run_id = commands.enqueue_run(
        project_id=project_id,
        idempotency_key=f"capture-{uuid4().hex}",
        task_type="source.capture",
        payload={"url": url},
    )
    captured = CapturedPage(
        requested_url=url,
        final_url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8", "etag": '"v1"'},
        body=(
            b"<html lang='en'><head><title>Version 1.2 Update Notes</title></head>"
            b"<body><main><h1>Version 1.2 Update Notes</h1>"
            b"<p>Official evidence captured by the durable worker.</p></main></body></html>"
        ),
        method=CaptureMethod.HTTP,
    )
    fetcher = StaticFetcher(captured)
    handler = SourceIngestionHandlers(
        adapters=(NteSiteAdapter(),),
        repository=DatabaseSourceRepository(factory),
        object_storage=LocalObjectStorage(tmp_path / "objects"),
        runtime_factory=lambda _: CaptureRuntime(
            http=fetcher,
            browser=fetcher,
            robots=AllowingRobots(),
        ),
        evidence_extractor=extract_evidence_document,
        timeout_seconds=1,
        html_max_bytes=100_000,
        image_max_bytes=10_000,
        max_images_per_page=2,
        max_redirects=2,
        quick_candidate_limit=30,
        targeted_candidate_limit=100,
    )
    worker = Worker(
        queue=DatabaseJobQueue(factory),
        handlers={"source.capture": handler.capture},
        worker_id="test-source-worker",
        lease_seconds=30,
    )

    assert worker.run_once() is True

    with factory() as session:
        run = session.get(WorkflowRunRecord, run_id)
        assert run is not None
        assert run.status == "succeeded"
        assert session.scalar(select(func.count()).select_from(SourceVersionRecord)) == 1
        event_types = set(session.scalars(select(AuditEventRecord.event_type)))
        assert {"source.version_captured", "job.completed"} <= event_types
