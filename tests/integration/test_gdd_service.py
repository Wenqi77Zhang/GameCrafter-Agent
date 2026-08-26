from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gamecrafter.infrastructure.database.gdd_service import DatabaseGddService, GddError
from gamecrafter.infrastructure.database.local_source_service import DatabaseLocalSourceService
from gamecrafter.infrastructure.database.models import AuditEventRecord, Base
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def _services(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(slug="gdd-test", name="GDD test")
    storage = LocalObjectStorage(tmp_path / "objects")
    local = DatabaseLocalSourceService(sessions, storage, max_bytes=1024 * 1024)
    gdd = DatabaseGddService(sessions, storage)
    return sessions, project_id, local, gdd


def test_gdd_chapters_keep_exact_offsets_and_assumptions_stay_explicit(tmp_path: Path) -> None:
    sessions, project_id, local, gdd = _services(tmp_path)
    source, _ = local.import_text(
        project_id=project_id,
        document_key="nte-design",
        kind="gdd",
        title="NTE design draft",
        filename="nte.md",
        content="# Vision\nUrban supernatural exploration.\n\n## Loop\nExplore, fight, recover.",
        media_type="text/markdown",
        locale="en",
        region="private",
        actor_id="owner",
        command_key="import-gdd-1",
    )
    document, created = gdd.create_document(
        project_id=project_id,
        source_version_id=UUID(str(source["source_version_id"])),
        actor_id="owner",
    )
    replay, replay_created = gdd.create_document(
        project_id=project_id,
        source_version_id=UUID(str(source["source_version_id"])),
        actor_id="owner",
    )
    assert created is True and replay_created is False and replay["id"] == document["id"]
    assert [item["title"] for item in document["chapters"]] == ["Vision", "Loop"]
    original = "# Vision\nUrban supernatural exploration.\n\n## Loop\nExplore, fight, recover."
    for chapter in document["chapters"]:
        assert original[chapter["start_offset"] : chapter["end_offset"]] == chapter["content"]

    assumption, added = gdd.add_assumption(
        project_id=project_id,
        document_id=UUID(str(document["id"])),
        chapter_id=UUID(str(document["chapters"][1]["id"])),
        statement="A 45-second TikTok should foreground traversal.",
        rationale="Marketing hypothesis, not a sourced game fact.",
        actor_id="owner",
        command_key="gdd-assumption-1",
    )
    assert added is True and assumption["status"] == "proposed"
    with pytest.raises(GddError, match="all GDD assumptions"):
        gdd.approve_revision(
            project_id=project_id,
            document_id=UUID(str(document["id"])),
            notes=None,
            actor_id="owner",
            command_key="gdd-revision-blocked",
        )
    gdd.decide_assumption(
        project_id=project_id,
        document_id=UUID(str(document["id"])),
        assumption_id=UUID(str(assumption["id"])),
        decision="approved",
        reason="Approved as an experiment, not a fact.",
        actor_id="owner",
    )
    revision, published = gdd.approve_revision(
        project_id=project_id,
        document_id=UUID(str(document["id"])),
        notes="First reviewed design baseline",
        actor_id="owner",
        command_key="gdd-revision-1",
    )
    assert published is True and revision["revision_number"] == 1
    assert revision["manifest"]["assumptions"][0]["status"] == "approved"
    reused, duplicate_created = gdd.approve_revision(
        project_id=project_id,
        document_id=UUID(str(document["id"])),
        notes="A duplicate click must not create redundant history",
        actor_id="owner",
        command_key="gdd-revision-duplicate-content",
    )
    assert duplicate_created is False
    assert reused["id"] == revision["id"]
    with sessions() as session:
        events = list(session.scalars(select(AuditEventRecord)))
    assert {item.event_type for item in events} >= {
        "gdd.document_structured",
        "gdd.assumption_proposed",
        "gdd.assumption_decided",
        "gdd.revision_approved",
    }
