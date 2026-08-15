import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.marketing_service import DatabaseMarketingService
from gamecrafter.infrastructure.database.models import (
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    SourceRecord,
    SourceVersionRecord,
    TrendSignalRecord,
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
        bind=create_engine(database_url, pool_pre_ping=True), expire_on_commit=False
    )


def test_postgres_freezes_manual_trend_fit_and_topic_decision() -> None:
    sessions = _sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"marketing-pg-{nonce}", name="异环 marketing PostgreSQL"
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="test-user",
    )
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
            subject_entity_id=UUID(str(entity["id"])),
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
        reason="Exact official title evidence.",
        actor_id="local-user",
        command_key=f"marketing-review-{nonce}",
    )
    snapshot, _ = DatabaseSnapshotService(sessions).publish(
        project_id=project_id,
        notes="PostgreSQL marketing baseline.",
        actor_id="local-user",
        command_key=f"marketing-snapshot-{nonce}",
    )
    service = DatabaseMarketingService(sessions)
    task, _ = service.create_task(
        project_id=project_id,
        knowledge_snapshot_id=UUID(str(snapshot["id"])),
        platform="TikTok",
        markets=["US"],
        audience="Potential new players",
        goal="Awareness",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key=f"marketing-task-{nonce}",
    )
    signal, _ = service.add_signal(
        project_id=project_id,
        source_name="TikTok Creative Center",
        source_url=f"https://ads.tiktok.com/business/creativecenter/{nonce}",
        observed_at=datetime.now(UTC),
        region="US",
        signal_type="hashtag",
        title="#NTE",
        keywords=["NTE", "Neverness to Everness"],
        metric_name="posts",
        metric_value=1250,
        notes="Manual public observation.",
        actor_id="local-user",
        command_key=f"marketing-trend-{nonce}",
    )
    candidates = service.analyze(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        actor_id="local-system",
    )
    review, _ = service.review_topic(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        candidate_id=UUID(str(candidates[0]["id"])),
        decision="approve",
        reason="Source, market, and knowledge fit verified.",
        actor_id="local-user",
        command_key=f"marketing-topic-review-{nonce}",
    )
    assert candidates[0]["score"] == 100 and review["decision"] == "approve"

    with pytest.raises(DBAPIError, match="immutable"), sessions.begin() as session:
        stored = session.scalar(
            select(TrendSignalRecord).where(TrendSignalRecord.id == UUID(str(signal["id"])))
        )
        assert stored is not None
        stored.title = "Silently rewritten trend"
