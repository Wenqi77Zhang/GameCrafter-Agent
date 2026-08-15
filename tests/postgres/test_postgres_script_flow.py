from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from test_postgres_marketing_flow import _sessions

from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.marketing_service import DatabaseMarketingService
from gamecrafter.infrastructure.database.models import (
    ClaimEvidenceSpanRecord,
    KnowledgeClaimRecord,
    ScriptVersionRecord,
    SourceRecord,
    SourceVersionRecord,
)
from gamecrafter.infrastructure.database.review_service import DatabaseReviewService
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.database.script_service import DatabaseScriptService
from gamecrafter.infrastructure.database.snapshot_service import DatabaseSnapshotService

pytestmark = pytest.mark.postgres


def test_postgres_freezes_script_versions_and_approved_export_lineage() -> None:
    sessions = _sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"script-pg-{nonce}", name="异环 script PostgreSQL"
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
            canonical_url=f"https://nte.perfectworld.com/en/script/{nonce}",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type="overview",
        )
        session.add(source)
        session.flush()
        source_version = SourceVersionRecord(
            source_id=source.id,
            version_number=1,
            title="NTE official script evidence",
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
        session.add_all([source_version, claim])
        session.flush()
        claim_id = claim.id
        session.add(
            ClaimEvidenceSpanRecord(
                claim_id=claim.id,
                source_version_id=source_version.id,
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
        command_key=f"script-review-{nonce}",
    )
    snapshot, _ = DatabaseSnapshotService(sessions).publish(
        project_id=project_id,
        notes="PostgreSQL script baseline.",
        actor_id="local-user",
        command_key=f"script-snapshot-{nonce}",
    )
    marketing = DatabaseMarketingService(sessions)
    task, _ = marketing.create_task(
        project_id=project_id,
        knowledge_snapshot_id=UUID(str(snapshot["id"])),
        platform="TikTok",
        markets=["US"],
        audience="Potential new players",
        goal="Awareness",
        output_language="en",
        duration_seconds=30,
        actor_id="local-user",
        command_key=f"script-task-{nonce}",
    )
    marketing.add_signal(
        project_id=project_id,
        source_name="TikTok Creative Center",
        source_url=f"https://ads.tiktok.com/business/creativecenter/script/{nonce}",
        observed_at=datetime.now(UTC),
        region="US",
        signal_type="hashtag",
        title="#NTE",
        keywords=["NTE"],
        metric_name="posts",
        metric_value=1000,
        notes="Manual public observation.",
        actor_id="local-user",
        command_key=f"script-signal-{nonce}",
    )
    candidate = marketing.analyze(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        actor_id="local-system",
    )[0]
    marketing.review_topic(
        project_id=project_id,
        task_id=UUID(str(task["id"])),
        candidate_id=UUID(str(candidate["id"])),
        decision="approve",
        reason="Topic lineage verified.",
        actor_id="local-user",
        command_key=f"script-topic-{nonce}",
    )
    scripts = DatabaseScriptService(sessions)
    run, _ = scripts.create_run(
        project_id=project_id,
        marketing_task_id=UUID(str(task["id"])),
        revision_budget=2,
        score_threshold=80,
        actor_id="local-user",
        command_key=f"script-run-{nonce}",
    )
    run_id = UUID(str(run["id"]))
    version, _ = scripts.generate(
        project_id=project_id,
        run_id=run_id,
        actor_id="local-system",
        command_key=f"script-generate-{nonce}",
    )
    version_id = UUID(str(version["id"]))
    evaluation, _ = scripts.evaluate(
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        command_key=f"script-evaluate-{nonce}",
    )
    assert evaluation["score"] == 100
    scripts.final_review(
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        decision="approve",
        reason="Exact version checked.",
        actor_id="local-user",
        command_key=f"script-final-{nonce}",
    )
    exported, _ = scripts.export(
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        format="json",
        command_key=f"script-export-{nonce}",
    )
    assert exported["sha256"] and exported["content"].endswith("\n")

    with pytest.raises(DBAPIError, match="immutable"), sessions.begin() as session:
        stored = session.scalar(
            select(ScriptVersionRecord).where(ScriptVersionRecord.id == version_id)
        )
        assert stored is not None
        stored.content = {"silently": "rewritten"}
