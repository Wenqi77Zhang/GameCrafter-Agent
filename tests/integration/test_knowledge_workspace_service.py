from hashlib import sha256
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.application.ports.knowledge_repository import KnowledgeStateError
from gamecrafter.infrastructure.database.knowledge_repository import DatabaseKnowledgeRepository
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
    KnowledgeWorkspaceConflictError,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_entity_corrections_and_archival_are_append_only() -> None:
    sessions = make_session_factory()
    project_id = DatabaseRunService(sessions).create_project(slug="nte", name="异环")
    service = DatabaseKnowledgeWorkspaceService(sessions)

    entity, created = service.create_entity(
        project_id=project_id,
        display_name="  异环  ",
        aliases=["NTE: Neverness to Everness", "异环", "NTE: Neverness to Everness"],
        actor_id="local-user",
    )

    assert created is True
    assert entity["canonical_key"] == "game:nte"
    assert entity["display_name"] == "异环"
    assert entity["aliases"] == ["NTE: Neverness to Everness"]
    assert entity["revision_number"] == 1

    duplicate, duplicate_created = service.create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE: Neverness to Everness"],
        actor_id="local-user",
    )
    assert duplicate_created is False
    assert duplicate["id"] == entity["id"]
    with pytest.raises(KnowledgeWorkspaceConflictError, match="duplicate"):
        service.create_entity(
            project_id=project_id,
            display_name="异环",
            aliases=["NTE: Neverness to Everness", "NTE"],
            actor_id="local-user",
        )

    corrected, changed = service.correct_entity(
        project_id=project_id,
        entity_id=UUID(str(entity["id"])),
        display_name="异环（Neverness to Everness）",
        aliases=["异环", "NTE"],
        change_reason="Correct the public display label.",
        actor_id="local-user",
    )
    assert changed is True
    assert corrected["revision_number"] == 2
    assert corrected["canonical_key"] == "game:nte"

    archived, archived_now = service.archive_entity(
        project_id=project_id,
        entity_id=UUID(str(entity["id"])),
        change_reason="Created the wrong subject.",
        actor_id="local-user",
    )
    assert archived_now is True
    assert archived["status"] == "archived"
    assert service.list_entities(project_id) == []
    assert service.list_entities(project_id, include_archived=True)[0]["status"] == "archived"

    revisions = service.list_entity_revisions(
        project_id=project_id,
        entity_id=UUID(str(entity["id"])),
    )
    assert [item["revision_number"] for item in revisions] == [1, 2, 3]
    assert [item["status"] for item in revisions] == ["active", "active", "archived"]
    with pytest.raises(KnowledgeWorkspaceConflictError, match="archived"):
        service.correct_entity(
            project_id=project_id,
            entity_id=UUID(str(entity["id"])),
            display_name="异环",
            aliases=["NTE"],
            change_reason="Do not revive an archived subject.",
            actor_id="local-user",
        )

    replacement, replacement_created = service.create_entity(
        project_id=project_id,
        display_name="异环（Neverness to Everness）",
        aliases=["异环", "NTE"],
        actor_id="local-user",
    )
    assert replacement_created is True
    assert replacement["id"] != entity["id"]
    assert replacement["canonical_key"].startswith("game:nte-")

    with sessions() as session:
        events = list(
            session.scalars(
                select(AuditEventRecord)
                .where(
                    AuditEventRecord.project_id == project_id,
                    AuditEventRecord.event_type.like("knowledge.entity_%"),
                )
                .order_by(AuditEventRecord.occurred_at, AuditEventRecord.id)
            )
        )
        assert [event.event_type for event in events] == [
            "knowledge.entity_created",
            "knowledge.entity_corrected",
            "knowledge.entity_archived",
            "knowledge.entity_created",
        ]


def test_source_version_read_model_marks_latest_and_extractable_text() -> None:
    sessions = make_session_factory()
    project_id = DatabaseRunService(sessions).create_project(slug="nte", name="异环")
    digest_one = sha256(b"version one").hexdigest()
    digest_two = sha256(b"version two").hexdigest()
    service = DatabaseKnowledgeWorkspaceService(sessions)
    entity, _ = service.create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="local-user",
    )
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url="https://nte.perfectworld.com/en/",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        session.add(source)
        session.flush()
        first = SourceVersionRecord(
            source_id=source.id,
            version_number=1,
            title="NTE v1",
            capture_method="http",
            change_kind="initial",
            raw_content_sha256=digest_one,
            normalized_text_sha256=digest_one,
            evidence_fingerprint_sha256=digest_one,
            parser_version="test",
            capture_policy_version="test",
        )
        second = SourceVersionRecord(
            source_id=source.id,
            previous_version_id=None,
            version_number=2,
            title="NTE v2",
            capture_method="http",
            change_kind="meaningful",
            raw_content_sha256=digest_two,
            normalized_text_sha256=digest_two,
            evidence_fingerprint_sha256=digest_two,
            parser_version="test",
            capture_policy_version="test",
        )
        stored = StoredObjectRecord(
            object_key=f"sha256/{digest_two[:2]}/{digest_two}",
            sha256=digest_two,
            size_bytes=len(b"version two"),
            media_type="text/plain; charset=utf-8",
            storage_backend="filesystem",
        )
        session.add_all([first, second, stored])
        session.flush()
        second.previous_version_id = first.id
        session.add(
            SourceAssetRecord(
                source_version_id=second.id,
                stored_object_id=stored.id,
                role="normalized_text",
                ordinal=0,
            )
        )
        second_version_id = second.id

    items = DatabaseKnowledgeWorkspaceService(sessions).list_source_versions(project_id)

    assert [item["version_number"] for item in items] == [2, 1]
    assert items[0]["is_latest"] is True
    assert items[0]["normalized_text_available"] is True
    assert items[1]["is_latest"] is False
    assert items[1]["normalized_text_available"] is False

    service.archive_entity(
        project_id=project_id,
        entity_id=UUID(str(entity["id"])),
        change_reason="The subject was created by mistake.",
        actor_id="local-user",
    )
    with pytest.raises(KnowledgeStateError, match="archived"):
        DatabaseKnowledgeRepository(sessions).validate_target(
            project_id=project_id,
            source_version_id=second_version_id,
            subject_entity_id=UUID(str(entity["id"])),
        )
