from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.knowledge_repository import DatabaseKnowledgeRepository
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.review_service import (
    DatabaseReviewService,
    ReviewServiceConflictError,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def _sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_conflict(
    sessions: sessionmaker[Session],
    *,
    relation: str = "conflicting",
) -> tuple[UUID, UUID, list[UUID]]:
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"review-{uuid4().hex}",
        name="Review fixture",
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
        claims = []
        for value in ("Neverness to Everness", "NTE"):
            normalized = value.casefold()
            claim = KnowledgeClaimRecord(
                project_id=project_id,
                subject_entity_id=entity_id,
                predicate="game.name" if relation == "conflicting" else "game.developer",
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
        group = ClaimConflictGroupRecord(
            project_id=project_id,
            subject_entity_id=entity_id,
            predicate=claims[0].predicate,
            scope_fingerprint_sha256=scope,
            status="open",
        )
        session.add(group)
        session.flush()
        session.add_all(
            [
                ClaimConflictMemberRecord(
                    conflict_group_id=group.id,
                    claim_id=claim.id,
                    relation=relation,
                    basis="test policy basis",
                )
                for claim in claims
            ]
        )
        return project_id, group.id, [claim.id for claim in claims]


def test_append_only_reviews_are_idempotent_and_resolve_one_winning_value() -> None:
    sessions = _sessions()
    project_id, group_id, claim_ids = _seed_conflict(sessions)
    service = DatabaseReviewService(sessions)

    with pytest.raises(ReviewServiceConflictError, match="every conflict member"):
        service.close_conflict(
            project_id=project_id,
            conflict_group_id=group_id,
            outcome="resolved",
            reason="Choose the exact official title.",
            actor_id="local-user",
            command_key="resolve-before-review",
        )

    approved, created = service.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve",
        approved_value=None,
        reason="The exact official title appears in the evidence.",
        actor_id="local-user",
        command_key="review-official-title",
    )
    replayed, replay_created = service.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve",
        approved_value=None,
        reason="The exact official title appears in the evidence.",
        actor_id="local-user",
        command_key="review-official-title",
    )
    assert created is True and replay_created is False
    assert replayed["id"] == approved["id"]
    with pytest.raises(ReviewServiceConflictError, match="idempotency key"):
        service.review_claim(
            project_id=project_id,
            claim_id=claim_ids[0],
            decision="reject",
            approved_value=None,
            reason="Reuse must fail.",
            actor_id="local-user",
            command_key="review-official-title",
        )

    service.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="reject",
        approved_value=None,
        reason="This abbreviation is not the primary official title.",
        actor_id="local-user",
        command_key="review-abbreviation",
    )
    closure, closure_created = service.close_conflict(
        project_id=project_id,
        conflict_group_id=group_id,
        outcome="resolved",
        reason="Keep the exact official title and reject the abbreviation as primary name.",
        actor_id="local-user",
        command_key="resolve-primary-title",
    )
    replayed_closure, replayed_closure_created = service.close_conflict(
        project_id=project_id,
        conflict_group_id=group_id,
        outcome="resolved",
        reason="Keep the exact official title and reject the abbreviation as primary name.",
        actor_id="local-user",
        command_key="resolve-primary-title",
    )
    assert closure_created is True and replayed_closure_created is False
    assert replayed_closure["id"] == closure["id"]
    assert replayed_closure["review_counts"] == closure["review_counts"]
    assert closure["status"] == "resolved"
    assert closure["review_counts"] == {"approve": 1, "reject": 1}

    claims = DatabaseKnowledgeRepository(sessions).list_claims(project_id)
    by_id = {item["id"]: item for item in claims}
    assert by_id[str(claim_ids[0])]["status"] == "human_approved"
    assert by_id[str(claim_ids[1])]["status"] == "human_rejected"
    assert len(by_id[str(claim_ids[0])]["reviews"]) == 1
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEventRecord)
                .where(AuditEventRecord.event_type == "knowledge.claim_reviewed")
            )
            == 2
        )


def test_review_edits_are_typed_and_possible_coexistence_allows_multiple_approvals() -> None:
    sessions = _sessions()
    project_id, group_id, claim_ids = _seed_conflict(
        sessions,
        relation="possibly_coexisting",
    )
    service = DatabaseReviewService(sessions)
    with pytest.raises(ReviewServiceConflictError, match="equivalent"):
        service.review_claim(
            project_id=project_id,
            claim_id=claim_ids[0],
            decision="approve_with_edit",
            approved_value="  Neverness to Everness  ",
            reason="No material edit.",
            actor_id="local-user",
            command_key="equivalent-edit",
        )
    with pytest.raises(ReviewServiceConflictError, match="16384"):
        service.review_claim(
            project_id=project_id,
            claim_id=claim_ids[0],
            decision="approve_with_edit",
            approved_value="x" * 16_385,
            reason="Reject an unbounded input before persistence.",
            actor_id="local-user",
            command_key="oversized-human-edit",
        )
    service.review_claim(
        project_id=project_id,
        claim_id=claim_ids[0],
        decision="approve_with_edit",
        approved_value="Hotta Studio",
        reason="Correct the organization name while retaining the source Claim.",
        actor_id="local-user",
        command_key="edited-developer",
    )
    service.review_claim(
        project_id=project_id,
        claim_id=claim_ids[1],
        decision="approve",
        approved_value=None,
        reason="A second organization may coexist for this multi-valued predicate.",
        actor_id="local-user",
        command_key="second-developer",
    )
    closure, _ = service.close_conflict(
        project_id=project_id,
        conflict_group_id=group_id,
        outcome="resolved",
        reason="Both organization statements may coexist after human review.",
        actor_id="local-user",
        command_key="resolve-coexisting-developers",
    )
    assert closure["review_counts"] == {"approve_with_edit": 1, "approve": 1}


def test_human_can_dismiss_a_false_positive_without_approving_claims() -> None:
    sessions = _sessions()
    project_id, group_id, _ = _seed_conflict(sessions)
    closure, created = DatabaseReviewService(sessions).close_conflict(
        project_id=project_id,
        conflict_group_id=group_id,
        outcome="dismissed",
        reason="Human verified that this group is not actionable.",
        actor_id="local-user",
        command_key="dismiss-false-positive",
    )
    assert created is True
    assert closure["status"] == "dismissed"
