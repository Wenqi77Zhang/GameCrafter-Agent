import os
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
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

pytestmark = pytest.mark.postgres


def postgres_sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True),
        expire_on_commit=False,
    )


def test_postgres_enforces_evidence_review_conflict_and_snapshot_lineage() -> None:
    sessions = postgres_sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"nte-knowledge-{nonce}",
        name="异环",
    )
    digest = sha256(nonce.encode()).hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url=f"https://nte.perfectworld.com/en/{nonce}.html",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        entity = KnowledgeEntityRecord(
            project_id=project_id,
            entity_type="game",
            canonical_key=f"game:nte:{nonce}",
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
            scope_fingerprint_sha256=digest,
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
        source_version_id = version.id
        claim_id = claim.id
        entity_id = entity.id

    with pytest.raises(DBAPIError, match="without evidence"), sessions.begin() as session:
        session.add(
            ClaimReviewRecord(
                project_id=project_id,
                claim_id=claim_id,
                decision="approve",
                approved_value_kind="string",
                approved_value="Neverness to Everness",
                approved_normalized_value="neverness to everness",
                reason="Exact official title.",
                reviewer_id="local-user",
            )
        )

    with sessions.begin() as session:
        session.add(
            ClaimEvidenceSpanRecord(
                claim_id=claim_id,
                source_version_id=source_version_id,
                ordinal=0,
                start_offset=0,
                end_offset=21,
                quote="Neverness to Everness",
                quote_sha256=sha256(b"Neverness to Everness").hexdigest(),
            )
        )
        review = ClaimReviewRecord(
            project_id=project_id,
            claim_id=claim_id,
            decision="approve",
            approved_value_kind="string",
            approved_value="Neverness to Everness",
            approved_normalized_value="neverness to everness",
            reason="Exact official title.",
            reviewer_id="local-user",
        )
        conflict = ClaimConflictGroupRecord(
            project_id=project_id,
            subject_entity_id=entity_id,
            predicate="game.name",
            scope_fingerprint_sha256=digest,
            status="open",
        )
        snapshot = KnowledgeSnapshotRecord(
            project_id=project_id,
            version_number=1,
            content_sha256=sha256(f"snapshot:{nonce}".encode()).hexdigest(),
            published_by="local-user",
        )
        session.add_all([review, conflict, snapshot])
        session.flush()
        session.add(
            ClaimConflictMemberRecord(
                conflict_group_id=conflict.id,
                claim_id=claim_id,
                relation="conflicting",
                basis="Same subject, predicate, and scope with different normalized values.",
            )
        )
        review_id = review.id
        conflict_id = conflict.id
        snapshot_id = snapshot.id

    with pytest.raises(DBAPIError, match="unresolved"), sessions.begin() as session:
        session.add(
            KnowledgeSnapshotMemberRecord(
                snapshot_id=snapshot_id,
                claim_id=claim_id,
                review_id=review_id,
            )
        )

    with sessions.begin() as session:
        conflict = session.get(ClaimConflictGroupRecord, conflict_id)
        assert conflict is not None
        conflict.status = "resolved"
        conflict.resolution_summary = "Human confirmed the official title."
        conflict.resolved_by = "local-user"

    with sessions.begin() as session:
        member = KnowledgeSnapshotMemberRecord(
            snapshot_id=snapshot_id,
            claim_id=claim_id,
            review_id=review_id,
        )
        session.add(member)
        session.flush()
        member_id = member.id

    with sessions() as session:
        assert session.get(KnowledgeSnapshotMemberRecord, member_id) is not None

    with pytest.raises(DBAPIError, match="immutable"), sessions.begin() as session:
        review = session.get(ClaimReviewRecord, review_id)
        assert review is not None
        review.reason = "Silently replaced review reason."


def test_postgres_rejects_cross_project_claim_subject() -> None:
    sessions = postgres_sessions()
    nonce = uuid4().hex
    service = DatabaseRunService(sessions)
    project_a = service.create_project(
        slug=f"knowledge-boundary-a-{nonce}",
        name="Project A",
    )
    project_b = service.create_project(
        slug=f"knowledge-boundary-b-{nonce}",
        name="Project B",
    )
    digest = sha256(nonce.encode()).hexdigest()

    with sessions.begin() as session:
        foreign_entity = KnowledgeEntityRecord(
            project_id=project_b,
            entity_type="game",
            canonical_key=f"game:foreign:{nonce}",
            display_name="Foreign game",
        )
        session.add(foreign_entity)
        session.flush()
        foreign_entity_id = foreign_entity.id

    with pytest.raises(DBAPIError, match="subject must stay"), sessions.begin() as session:
        session.add(
            KnowledgeClaimRecord(
                project_id=project_a,
                subject_entity_id=foreign_entity_id,
                predicate="game.name",
                value_kind="string",
                value="Foreign game",
                normalized_value="foreign game",
                value_fingerprint_sha256=digest,
                scope_fingerprint_sha256=digest,
                confidence=0.75,
                locale="en",
                region="global",
                model_provider="fixture",
                model_name="fixture",
                prompt_version="claim-v1",
                schema_version="claim-v1",
            )
        )
