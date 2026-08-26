from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.marketing_service import (
    DatabaseMarketingService,
    MarketingServiceConflictError,
)
from gamecrafter.infrastructure.database.models import (
    Base,
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.review_service import DatabaseReviewService
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.snapshot_service import DatabaseSnapshotService


def _seed() -> tuple[sessionmaker[Session], UUID, UUID]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"marketing-{uuid4().hex}", name="异环 marketing"
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE", "Neverness to Everness"],
        actor_id="test-user",
    )
    digest = sha256(uuid4().bytes).hexdigest()
    with sessions.begin() as session:
        source = SourceRecord(
            project_id=project_id,
            canonical_url="https://nte.perfectworld.com/en/main.html",
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
        command_key="marketing-review-title",
    )
    snapshot, _ = DatabaseSnapshotService(sessions).publish(
        project_id=project_id,
        notes="Marketing knowledge baseline.",
        actor_id="local-user",
        command_key="marketing-publish-snapshot",
    )
    return sessions, project_id, UUID(str(snapshot["id"]))


def test_manual_trend_to_explainable_human_approved_topic() -> None:
    sessions, project_id, snapshot_id = _seed()
    service = DatabaseMarketingService(sessions)
    task, created = service.create_task(
        project_id=project_id,
        knowledge_snapshot_id=snapshot_id,
        platform="TikTok",
        markets=["US", "UK", "US"],
        audience="Potential new players in English-speaking markets",
        goal="Drive qualified awareness for NTE",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key="marketing-task-nte-en",
    )
    assert created is True and task["markets"] == ["UK", "US"]
    replay, replay_created = service.create_task(
        project_id=project_id,
        knowledge_snapshot_id=snapshot_id,
        platform="TikTok",
        markets=["UK", "US"],
        audience="Potential new players in English-speaking markets",
        goal="Drive qualified awareness for NTE",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key="marketing-task-nte-en",
    )
    assert replay_created is False and replay == task

    signal, signal_created = service.add_signal(
        project_id=project_id,
        source_name="TikTok Creative Center",
        source_url="https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
        observed_at=datetime.now(UTC) - timedelta(days=1),
        region="US",
        signal_type="hashtag",
        title="#NTE",
        keywords=["NTE", "Neverness to Everness"],
        metric_name="posts",
        metric_value=1250,
        notes="Manually verified public observation; no automated scraping.",
        actor_id="local-user",
        command_key="trend-signal-nte-hashtag",
    )
    assert signal_created is True and signal["metric_value"] == 1250
    assert signal["processing"]["version"] == "trend-processing-v1"
    assert signal["processing"]["normalized_title"] == "nte"
    assert signal["processing"]["freshness"] == "fresh"

    candidates = service.analyze(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        actor_id="local-system",
    )
    assert len(candidates) == 1
    assert candidates[0]["score"] == 100
    assert candidates[0]["rule_version"] == "trend-fit-v1"
    assert candidates[0]["matched_snapshot_member_ids"]
    assert "No model was used" in candidates[0]["rationale"]

    review, review_created = service.review_topic(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        candidate_id=UUID(str(candidates[0]["id"])),
        decision="approve",
        reason="Strong current US signal with exact NTE knowledge overlap.",
        actor_id="local-user",
        command_key="topic-approve-nte-hashtag",
    )
    assert review_created is True and review["decision"] == "approve"
    updated = service.get_task(project_id=project_id, task_id=UUID(str(task["id"])))
    assert updated["approved_candidate_id"] == candidates[0]["id"]


def test_trend_read_model_normalizes_deduplicates_and_clusters_without_mutating_raw_rows() -> None:
    sessions, project_id, _ = _seed()
    service = DatabaseMarketingService(sessions)
    for index, title in enumerate(("#Cozy Gaming", "cozy-gaming")):
        service.add_signal(
            project_id=project_id,
            source_name=f"Verified source {index}",
            source_url=f"https://example.com/trends/{index}",
            observed_at=datetime.now(UTC) - timedelta(days=index),
            region="US",
            signal_type="topic",
            title=title,
            keywords=["cozy", "gaming"],
            metric_name=None,
            metric_value=None,
            notes="Manual public observation.",
            actor_id="local-user",
            command_key=f"trend-processing-{index}",
        )

    signals = service.list_signals(project_id)
    assert len(signals) == 2
    assert {item["processing"]["normalized_title"] for item in signals} == {"cozy gaming"}
    assert {item["processing"]["cluster_size"] for item in signals} == {2}
    assert sum(item["processing"]["duplicate_of_signal_id"] is not None for item in signals) == 1


def test_trend_validation_and_single_approved_topic_gate() -> None:
    sessions, project_id, snapshot_id = _seed()
    service = DatabaseMarketingService(sessions)
    task, _ = service.create_task(
        project_id=project_id,
        knowledge_snapshot_id=snapshot_id,
        platform="TikTok",
        markets=["US"],
        audience="New players",
        goal="Awareness",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key="marketing-task-validation",
    )
    with pytest.raises(MarketingServiceConflictError, match="HTTPS"):
        service.add_signal(
            project_id=project_id,
            source_name="Unsafe source",
            source_url="http://example.com/trend",
            observed_at=datetime.now(UTC),
            region="US",
            signal_type="topic",
            title="trend",
            keywords=[],
            metric_name=None,
            metric_value=None,
            notes=None,
            actor_id="local-user",
            command_key="unsafe-trend-signal",
        )
    for index, title in enumerate(("#NTE", "Open world")):
        service.add_signal(
            project_id=project_id,
            source_name="Manual public trend source",
            source_url=f"https://example.com/trend/{index}",
            observed_at=datetime.now(UTC),
            region="US",
            signal_type="topic",
            title=title,
            keywords=[title],
            metric_name=None,
            metric_value=None,
            notes="Manual observation.",
            actor_id="local-user",
            command_key=f"validation-trend-{index}",
        )
    candidates = service.analyze(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        actor_id="local-system",
    )
    service.review_topic(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        candidate_id=UUID(str(candidates[0]["id"])),
        decision="approve",
        reason="Approve the first candidate.",
        actor_id="local-user",
        command_key="approve-first-topic",
    )
    with pytest.raises(MarketingServiceConflictError, match="currently approved"):
        service.review_topic(
            project_id=project_id,
            task_id=UUID(str(task["id"])),
            candidate_id=UUID(str(candidates[1]["id"])),
            decision="approve",
            reason="Attempt to approve a second candidate.",
            actor_id="local-user",
            command_key="approve-second-topic",
        )
