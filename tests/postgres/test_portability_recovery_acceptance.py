"""Real PostgreSQL round-trip acceptance for verified project disaster recovery."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.local_source_service import DatabaseLocalSourceService
from gamecrafter.infrastructure.database.models import (
    ProjectRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.project_portability import (
    DatabaseProjectPortabilityService,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

pytestmark = pytest.mark.postgres


def _sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    if (
        "test" not in (parsed.database or "").lower()
        and "acceptance" not in (parsed.database or "").lower()
    ):
        pytest.fail("recovery acceptance requires a disposable test or acceptance database")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True), expire_on_commit=False
    )


def test_postgres_private_evidence_survives_verified_export_delete_restore(
    tmp_path: Path,
) -> None:
    sessions = _sessions()
    slug = f"recovery-{uuid4().hex}"
    project_id = DatabaseRunService(sessions).create_project(slug=slug, name="Recovery acceptance")
    storage = LocalObjectStorage(tmp_path / "objects")
    DatabaseLocalSourceService(sessions, storage, max_bytes=1024 * 1024).import_text(
        project_id=project_id,
        document_key="owned-gdd",
        kind="gdd",
        title="Owned design notes",
        filename="gdd.md",
        content="# World\nThe city changes after midnight.",
        media_type="text/markdown",
        locale="en",
        region="private",
        actor_id="m12-acceptance",
        command_key=f"restore-{uuid4().hex}",
    )
    service = DatabaseProjectPortabilityService(sessions, storage)
    _, archive = service.export_zip(project_id)
    service.delete_project(project_id=project_id, confirmation=f"DELETE {slug}")
    restored = service.restore_zip(archive)
    assert restored["project_id"] == str(project_id)
    with sessions() as session:
        assert session.get(ProjectRecord, UUID(str(project_id))) is not None
        assert session.scalar(
            select(SourceVersionRecord.id)
            .join(SourceRecord, SourceRecord.id == SourceVersionRecord.source_id)
            .where(SourceRecord.project_id == project_id)
        )
    service.delete_project(project_id=project_id, confirmation=f"DELETE {slug}")
