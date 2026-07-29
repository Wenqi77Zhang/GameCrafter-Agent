import os
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService

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
