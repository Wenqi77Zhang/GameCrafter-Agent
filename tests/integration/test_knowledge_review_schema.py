from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.infrastructure.database.models import (
    Base,
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRecord,
    KnowledgeSnapshotMemberRecord,
    KnowledgeSnapshotRecord,
    SourceRecord,
    SourceVersionRecord,
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


def seed_reviewable_claim(
    sessions: sessionmaker[Session],
) -> tuple[object, object, object, object]:
    project_id = DatabaseRunService(sessions).create_project(
        slug="nte-knowledge",
        name="异环",
    )
    digest = sha256(b"evidence").hexdigest()
    scope = sha256(b"global:all-time").hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url="https://nte.perfectworld.com/en/",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        entity = KnowledgeEntityRecord(
            project_id=project_id,
            entity_type="game",
            canonical_key="game:nte",
            display_name="Neverness to Everness",
        )
        session.add_all([source, entity])
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
            subject_entity_id=entity.id,
            predicate="game.name",
            value_kind="string",
            value="Neverness to Everness",
            normalized_value="neverness to everness",
            value_fingerprint_sha256=digest,
            scope_fingerprint_sha256=scope,
            confidence=0.95,
            locale="en",
            region="global",
            model_provider="fixture",
            model_name="fixture",
            prompt_version="claim-v1",
            schema_version="claim-v1",
        )
        session.add_all([version, claim])
        session.flush()
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
        return project_id, claim.id, entity.id, version.id


def test_approved_review_can_be_pinned_to_an_immutable_snapshot_member() -> None:
    sessions = make_session_factory()
    project_id, claim_id, _, _ = seed_reviewable_claim(sessions)
    with sessions.begin() as session:
        review = ClaimReviewRecord(
            project_id=project_id,
            claim_id=claim_id,
            decision="approve",
            approved_value_kind="string",
            approved_value="Neverness to Everness",
            approved_normalized_value="neverness to everness",
            reason="Matches the exact official title.",
            reviewer_id="local-user",
        )
        snapshot = KnowledgeSnapshotRecord(
            project_id=project_id,
            version_number=1,
            content_sha256=sha256(b"snapshot-1").hexdigest(),
            published_by="local-user",
        )
        session.add_all([review, snapshot])
        session.flush()
        member = KnowledgeSnapshotMemberRecord(
            snapshot_id=snapshot.id,
            claim_id=claim_id,
            review_id=review.id,
        )
        session.add(member)
        session.flush()
        member_id = member.id

    with sessions() as session:
        member = session.get(KnowledgeSnapshotMemberRecord, member_id)
        assert member is not None
        assert member.review_id == review.id


def test_database_rejects_out_of_range_confidence() -> None:
    sessions = make_session_factory()
    project_id, _, entity_id, _ = seed_reviewable_claim(sessions)
    digest = sha256(b"invalid").hexdigest()
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            KnowledgeClaimRecord(
                project_id=project_id,
                subject_entity_id=entity_id,
                predicate="game.name",
                value_kind="string",
                value="invented",
                normalized_value="invented",
                value_fingerprint_sha256=digest,
                scope_fingerprint_sha256=digest,
                confidence=1.1,
                locale="en",
                region="global",
                model_provider="fixture",
                model_name="fixture",
                prompt_version="claim-v1",
                schema_version="claim-v1",
            )
        )


def test_non_approval_review_cannot_carry_an_approved_value() -> None:
    sessions = make_session_factory()
    project_id, claim_id, _, _ = seed_reviewable_claim(sessions)
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            ClaimReviewRecord(
                project_id=project_id,
                claim_id=claim_id,
                decision="reject",
                approved_value_kind="string",
                approved_value="Neverness to Everness",
                approved_normalized_value="neverness to everness",
                reason="Test invalid review.",
                reviewer_id="local-user",
            )
        )
