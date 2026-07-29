import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.ports.object_storage import StoredObject
from gamecrafter.application.ports.site_adapter import AdaptedSource
from gamecrafter.application.ports.source_repository import PreparedCapture
from gamecrafter.domain.knowledge.sources import CaptureMethod, EvidenceDigest, SourceType
from gamecrafter.infrastructure.database.models import (
    IngestionRunRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.source_repository import DatabaseSourceRepository

pytestmark = pytest.mark.postgres


def postgres_sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True), expire_on_commit=False
    )


def test_source_versions_are_immutable_in_postgresql() -> None:
    sessions = postgres_sessions()
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"nte-evidence-{uuid4().hex}",
        name="异环",
    )
    raw_digest = sha256(b"<main>official evidence</main>").hexdigest()
    text_digest = sha256(b"official evidence").hexdigest()
    fingerprint = sha256(f"{raw_digest}:{text_digest}".encode()).hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=f"https://nte.perfectworld.com/en/{uuid4().hex}.html",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="news",
        )
        session.add(source)
        session.flush()
        version = SourceVersionRecord(
            source_id=source.id,
            version_number=1,
            title="Official evidence",
            capture_method="http",
            change_kind="initial",
            raw_content_sha256=raw_digest,
            normalized_text_sha256=text_digest,
            evidence_fingerprint_sha256=fingerprint,
            parser_version="test-parser-v1",
            capture_policy_version="test-policy-v1",
        )
        session.add(version)
        session.flush()
        version_id = version.id

    with pytest.raises(DBAPIError, match="immutable"), sessions.begin() as session:
        version = session.get(SourceVersionRecord, version_id)
        assert version is not None
        version.title = "Silently replaced evidence"


def test_capture_repository_is_idempotent_in_postgresql() -> None:
    sessions = postgres_sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"nte-capture-{nonce}",
        name="异环",
    )
    with sessions.begin() as session:
        run = IngestionRunRecord(
            project_id=project_id,
            idempotency_key=f"capture-{nonce}",
        )
        session.add(run)
        session.flush()
        run_id = run.id
    raw = f"<main>official {nonce}</main>".encode()
    normalized = f"official {nonce}".encode()

    def stored(body: bytes, media_type: str) -> StoredObject:
        digest = sha256(body).hexdigest()
        return StoredObject(
            key=f"sha256/{digest[:2]}/{digest}",
            digest=EvidenceDigest(digest),
            size_bytes=len(body),
            media_type=media_type,
        )

    raw_object = stored(raw, "text/html")
    normalized_object = stored(normalized, "text/plain; charset=utf-8")
    fingerprint = sha256(f"parser\0{normalized_object.digest.value}\0".encode()).hexdigest()
    article_id = uuid4().int
    capture = PreparedCapture(
        source=AdaptedSource(
            canonical_url=(
                f"https://nte.perfectworld.com/en/article/news/gamenews/20260706/{article_id}.html"
            ),
            site_key="nte-global",
            locale="en",
            region="global",
            source_type=SourceType.UPDATE,
            raw_category="gamenews",
            classification_basis="test",
        ),
        title="Official update",
        published_at=None,
        fetched_at=datetime.now(UTC),
        capture_method=CaptureMethod.HTTP,
        http_status=200,
        etag='"v1"',
        last_modified=None,
        raw_object=raw_object,
        normalized_object=normalized_object,
        images=(),
        image_candidate_count=0,
        image_failure_count=0,
        evidence_fingerprint_sha256=fingerprint,
        parser_version="parser-v1",
        capture_policy_version="policy-v1",
        document_language="en",
    )
    repository = DatabaseSourceRepository(sessions)

    first = repository.persist_capture(run_id=run_id, candidate_id=None, capture=capture)
    duplicate = repository.persist_capture(run_id=run_id, candidate_id=None, capture=capture)

    assert first.created_version is True
    assert duplicate.created_version is False
    assert duplicate.source_version_id == first.source_version_id
