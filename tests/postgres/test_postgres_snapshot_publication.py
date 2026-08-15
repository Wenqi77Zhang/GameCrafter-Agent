import os
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRevisionRecord,
    KnowledgeSnapshotMemberRecord,
    KnowledgeSnapshotRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.review_service import DatabaseReviewService
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.snapshot_service import DatabaseSnapshotService

pytestmark = pytest.mark.postgres


def _sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True),
        expire_on_commit=False,
    )


def test_postgres_publishes_idempotent_immutable_review_lineage() -> None:
    sessions = _sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"snapshot-acceptance-{nonce}",
        name="异环 snapshot acceptance",
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="test-user",
    )
    entity_id = UUID(str(entity["id"]))
    digest = sha256(nonce.encode()).hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=f"https://nte.perfectworld.com/en/{nonce}",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        session.add(source)
        session.flush()
        version = SourceVersionRecord(
            source_id=source.id,
            version_number=1,
            title="NTE official homepage",
            capture_method="http",
            change_kind="initial",
            raw_content_sha256=digest,
            normalized_text_sha256=digest,
            evidence_fingerprint_sha256=digest,
            parser_version="test",
            capture_policy_version="test",
        )
        claim = KnowledgeClaimRecord(
            project_id=project_id,
            subject_entity_id=entity_id,
            predicate="game.name",
            value_kind="string",
            value="Neverness to Everness",
            normalized_value="neverness to everness",
            value_fingerprint_sha256=digest,
            scope_fingerprint_sha256=digest,
            confidence=0.95,
            locale="en",
            region="global",
            model_provider="replay",
            model_name="fixture",
            prompt_version="claim-v1",
            schema_version="claim-v1",
        )
        session.add_all([version, claim])
        session.flush()
        claim_id = claim.id
        session.add(
            ClaimEvidenceSpanRecord(
                claim_id=claim.id,
                source_version_id=version.id,
                ordinal=0,
                start_offset=0,
                end_offset=21,
                quote="Neverness to Everness",
                quote_sha256=sha256(b"Neverness to Everness").hexdigest(),
            )
        )

    DatabaseReviewService(sessions).review_claim(
        project_id=project_id,
        claim_id=claim_id,
        decision="approve",
        approved_value=None,
        reason="The exact official title is supported by exact evidence.",
        actor_id="local-user",
        command_key=f"snapshot-review-{nonce}",
    )
    service = DatabaseSnapshotService(sessions)
    first, created = service.publish(
        project_id=project_id,
        notes="Reviewed NTE snapshot acceptance.",
        actor_id="local-user",
        command_key=f"snapshot-publish-{nonce}",
    )
    replayed, replay_created = service.publish(
        project_id=project_id,
        notes="Reviewed NTE snapshot acceptance.",
        actor_id="local-user",
        command_key=f"snapshot-publish-{nonce}",
    )
    assert created is True and replay_created is False
    assert replayed == first
    assert first["member_count"] == 1
    snapshot_id = UUID(str(first["id"]))

    with pytest.raises(DBAPIError, match="immutable"), sessions.begin() as session:
        snapshot = session.get(KnowledgeSnapshotRecord, snapshot_id)
        assert snapshot is not None
        snapshot.notes = "Attempted mutation."

    with sessions() as session:
        member = session.scalar(
            select(KnowledgeSnapshotMemberRecord).where(
                KnowledgeSnapshotMemberRecord.snapshot_id == snapshot_id
            )
        )
        assert member is not None and member.entity_revision_id is not None
        revision = session.get(KnowledgeEntityRevisionRecord, member.entity_revision_id)
        assert revision is not None and revision.entity_id == entity_id
        event = session.scalar(
            select(AuditEventRecord).where(
                AuditEventRecord.project_id == project_id,
                AuditEventRecord.event_type == "knowledge.snapshot_published",
            )
        )
        assert event is not None
        assert event.payload["content_sha256"] == first["content_sha256"]
