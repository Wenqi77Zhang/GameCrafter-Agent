from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.conflict_service import DatabaseConflictService
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    KnowledgeSnapshotMemberRecord,
    KnowledgeSnapshotRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.review_service import DatabaseReviewService
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.snapshot_service import (
    DatabaseSnapshotService,
    SnapshotServiceConflictError,
)


def _sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed(
    values: tuple[str, str] = ("Neverness to Everness", "NTE"),
) -> tuple[sessionmaker[Session], UUID, UUID, list[UUID]]:
    sessions = _sessions()
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"snapshot-{uuid4().hex}",
        name="异环 snapshot fixture",
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="test-user",
    )
    entity_id = UUID(str(entity["id"]))
    digest = sha256(uuid4().bytes).hexdigest()
    scope = sha256(b"en:global:timeless").hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=f"https://nte.perfectworld.com/en/{uuid4().hex}",
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
        session.add(version)
        session.flush()
        claims: list[KnowledgeClaimRecord] = []
        for value in values:
            normalized = value.casefold()
            claim = KnowledgeClaimRecord(
                project_id=project_id,
                subject_entity_id=entity_id,
                predicate="game.name",
                value_kind="string",
                value=value,
                normalized_value=normalized,
                value_fingerprint_sha256=sha256(normalized.encode()).hexdigest(),
                scope_fingerprint_sha256=scope,
                confidence=0.9,
                locale="en",
                region="global",
                model_provider="replay",
                model_name="fixture",
                prompt_version="claim-v1",
                schema_version="claim-v1",
            )
            session.add(claim)
            session.flush()
            session.add(
                ClaimEvidenceSpanRecord(
                    claim_id=claim.id,
                    source_version_id=version.id,
                    ordinal=0,
                    start_offset=0,
                    end_offset=len(value),
                    quote=value,
                    quote_sha256=sha256(value.encode()).hexdigest(),
                )
            )
            claims.append(claim)
    DatabaseConflictService(sessions).reconcile(project_id=project_id, actor_id="test-user")
    with sessions() as session:
        group_id = session.scalar(select(KnowledgeSnapshotRecord.id))
        assert group_id is None
    return sessions, project_id, entity_id, [claim.id for claim in claims]


def test_publication_requires_complete_reviews_and_closed_conflicts() -> None:
    sessions, project_id, _, claim_ids = _seed()
    snapshots = DatabaseSnapshotService(sessions)
    reviews = DatabaseReviewService(sessions)

    blocked = snapshots.readiness(project_id)
    assert blocked["publishable"] is False
    assert {item["code"] for item in blocked["blockers"]} == {
        "unreviewed_claims",
        "no_approved_claims",
        "open_conflicts",
    }

    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve",
        approved_value=None,
        reason="The exact official title is supported by evidence.",
        actor_id="local-user",
        command_key="snapshot-review-title",
    )
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="reject",
        approved_value=None,
        reason="The abbreviation is not the primary title.",
        actor_id="local-user",
        command_key="snapshot-review-alias",
    )
    group_id = UUID(
        str(DatabaseConflictService(sessions).list_conflicts(project_id, status="open")[0]["id"])
    )
    reviews.close_conflict(
        project_id=project_id,
        conflict_group_id=group_id,
        outcome="resolved",
        reason="Retain the exact official primary title.",
        actor_id="local-user",
        command_key="snapshot-resolve-title",
    )

    ready = snapshots.readiness(project_id)
    assert ready["publishable"] is True
    assert ready["stats"]["approved_count"] == 1
    assert len(ready["content_sha256"]) == 64


def test_snapshot_is_atomic_versioned_and_exactly_idempotent() -> None:
    sessions, project_id, entity_id, claim_ids = _seed()
    reviews = DatabaseReviewService(sessions)
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve",
        approved_value=None,
        reason="Use the exact official title.",
        actor_id="local-user",
        command_key="publish-review-title",
    )
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="reject",
        approved_value=None,
        reason="Reject the abbreviation as primary title.",
        actor_id="local-user",
        command_key="publish-review-alias",
    )
    conflict = DatabaseConflictService(sessions).list_conflicts(project_id, status="open")[0]
    reviews.close_conflict(
        project_id=project_id,
        conflict_group_id=UUID(str(conflict["id"])),
        outcome="resolved",
        reason="One approved primary title remains.",
        actor_id="local-user",
        command_key="publish-resolve-title",
    )
    service = DatabaseSnapshotService(sessions)

    first, created = service.publish(
        project_id=project_id,
        notes="NTE reviewed baseline.",
        actor_id="local-user",
        command_key="publish-snapshot-v1",
    )
    replayed, replay_created = service.publish(
        project_id=project_id,
        notes="NTE reviewed baseline.",
        actor_id="local-user",
        command_key="publish-snapshot-v1",
    )
    assert created is True and replay_created is False
    assert replayed == first
    assert first["version_number"] == 1
    assert first["schema_version"] == "knowledge-snapshot-v1"
    assert first["member_count"] == 1
    assert first["members"][0]["value"] == "Neverness to Everness"
    assert first["members"][0]["subject"]["display_name"] == "异环"
    assert first["members"][0]["subject"]["revision_number"] == 1
    assert first["members"][0]["evidence"][0]["quote"] == "Neverness to Everness"
    assert len(first["content_sha256"]) == 64
    with pytest.raises(SnapshotServiceConflictError, match="idempotency key"):
        service.publish(
            project_id=project_id,
            notes="Different command content.",
            actor_id="local-user",
            command_key="publish-snapshot-v1",
        )

    DatabaseKnowledgeWorkspaceService(sessions).correct_entity(
        project_id=project_id,
        entity_id=entity_id,
        display_name="异环（已核对）",
        aliases=["NTE"],
        change_reason="Clarify the user-facing entity label after the first publication.",
        actor_id="local-user",
    )
    second, second_created = service.publish(
        project_id=project_id,
        notes="Explicit second publication of the same reviewed state.",
        actor_id="local-user",
        command_key="publish-snapshot-v2",
    )
    assert second_created is True and second["version_number"] == 2
    assert second["content_sha256"] != first["content_sha256"]
    assert second["members"][0]["subject"]["display_name"] == "异环（已核对）"
    assert second["members"][0]["subject"]["revision_number"] == 2
    versions = service.list_snapshots(project_id)
    assert [item["version_number"] for item in versions] == [2, 1]
    assert versions[1]["members"][0]["subject"]["display_name"] == "异环"
    assert versions[1]["members"][0]["subject"]["revision_number"] == 1

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeSnapshotRecord)) == 2
        assert session.scalar(select(func.count()).select_from(KnowledgeSnapshotMemberRecord)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEventRecord)
                .where(AuditEventRecord.event_type == "knowledge.snapshot_published")
            )
            == 2
        )


def test_changed_reviews_cannot_bypass_closed_single_value_policy() -> None:
    sessions, project_id, _, claim_ids = _seed()
    reviews = DatabaseReviewService(sessions)
    for index, claim_id in enumerate(claim_ids):
        reviews.review_claim(
            project_id=project_id,
            claim_id=claim_id,
            decision="approve" if index == 0 else "reject",
            approved_value=None,
            reason=f"Initial final review {index}.",
            actor_id="local-user",
            command_key=f"stale-initial-review-{index}",
        )
    conflict = DatabaseConflictService(sessions).list_conflicts(project_id, status="open")[0]
    reviews.close_conflict(
        project_id=project_id,
        conflict_group_id=UUID(str(conflict["id"])),
        outcome="resolved",
        reason="Initial single-value resolution.",
        actor_id="local-user",
        command_key="stale-initial-resolution",
    )
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="approve",
        approved_value=None,
        reason="A later review now approves the conflicting abbreviation.",
        actor_id="local-user",
        command_key="stale-conflicting-review",
    )

    readiness = DatabaseSnapshotService(sessions).readiness(project_id)
    assert readiness["publishable"] is False
    assert "inconsistent_closed_conflict" in {item["code"] for item in readiness["blockers"]}


def test_human_edits_cannot_create_an_untracked_single_value_conflict() -> None:
    sessions, project_id, _, claim_ids = _seed(values=("NTE", "NTE"))
    reviews = DatabaseReviewService(sessions)
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve",
        approved_value=None,
        reason="Retain the first reviewed value.",
        actor_id="local-user",
        command_key="edit-conflict-original",
    )
    reviews.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="approve_with_edit",
        approved_value="Neverness to Everness",
        reason="This edit introduces a second approved primary name.",
        actor_id="local-user",
        command_key="edit-conflict-changed",
    )

    readiness = DatabaseSnapshotService(sessions).readiness(project_id)
    assert readiness["publishable"] is False
    assert "inconsistent_approved_values" in {item["code"] for item in readiness["blockers"]}
