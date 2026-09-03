from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.local_source_service import (
    DatabaseLocalSourceService,
    LocalSourceError,
)
from gamecrafter.infrastructure.database.models import Base, SourceAssetRecord, StoredObjectRecord
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def _service(tmp_path: Path) -> tuple[DatabaseLocalSourceService, sessionmaker[Session], object]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(
        slug="local-evidence", name="Local evidence"
    )
    return (
        DatabaseLocalSourceService(
            sessions,
            LocalObjectStorage(tmp_path / "objects"),
            max_bytes=1024 * 1024,
        ),
        sessions,
        project_id,
    )


def test_local_transcript_is_private_versioned_evidence_with_exact_normalized_text(
    tmp_path: Path,
) -> None:
    service, sessions, project_id = _service(tmp_path)
    first, created = service.import_text(
        project_id=project_id,
        document_key="nte-interview",
        kind="transcript",
        title="NTE creator interview",
        filename="interview.vtt",
        content="WEBVTT\r\n\r\n00:00.000 --> 00:02.000\r\nWelcome to Hethereau.",
        media_type="text/vtt",
        locale="en",
        region="private",
        actor_id="owner",
        command_key="local-transcript-import-1",
    )
    replay, replay_created = service.import_text(
        project_id=project_id,
        document_key="nte-interview",
        kind="transcript",
        title="NTE creator interview",
        filename="interview.vtt",
        content="WEBVTT\r\n\r\n00:00.000 --> 00:02.000\r\nWelcome to Hethereau.",
        media_type="text/vtt",
        locale="en",
        region="private",
        actor_id="owner",
        command_key="local-transcript-import-1",
    )

    assert created is True and replay_created is False and replay == first
    assert first["private"] is True and first["capture_method"] == "local_upload"
    with sessions() as session:
        assets = list(
            session.scalars(
                select(SourceAssetRecord).where(
                    SourceAssetRecord.source_version_id == UUID(str(first["source_version_id"]))
                )
            )
        )
        assert {asset.role for asset in assets} == {"raw_document", "normalized_text"}
        normalized_asset = next(asset for asset in assets if asset.role == "normalized_text")
        stored = session.get(StoredObjectRecord, normalized_asset.stored_object_id)
        assert stored is not None
    with service._storage.open(stored.object_key) as handle:  # noqa: SLF001 - verifies boundary
        assert handle.read().decode() == "WEBVTT\n\n00:00.000 --> 00:02.000\nWelcome to Hethereau."


def test_local_source_rejects_changed_payload_under_same_command(tmp_path: Path) -> None:
    service, _, project_id = _service(tmp_path)
    values = dict(
        project_id=project_id,
        document_key="design-notes",
        kind="document",
        title="Design notes",
        filename="notes.md",
        media_type="text/markdown",
        locale="en",
        region="private",
        actor_id="owner",
        command_key="local-document-import-1",
    )
    service.import_text(content="# First", **values)
    with pytest.raises(LocalSourceError, match="different local content"):
        service.import_text(content="# Changed", **values)
