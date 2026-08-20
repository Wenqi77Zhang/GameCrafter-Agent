from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from gamecrafter.application.ports.review_gateway import AgentClaimDecision
from gamecrafter.infrastructure.database.agent_review_service import DatabaseAgentReviewService
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    Base,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    WorkflowRunRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def test_agent_governance_and_batch_confirmation_remain_separate() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"agent-review-{uuid4().hex}", name="Agent review fixture"
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="test-user",
    )
    entity_id = UUID(str(entity["id"]))
    extraction_run_id, reviewer_run_id = uuid4(), uuid4()
    claim_ids: list[UUID] = []
    with sessions.begin() as session:
        session.add_all(
            [
                WorkflowRunRecord(
                    id=extraction_run_id,
                    project_id=project_id,
                    idempotency_key="extract-agent-review-fixture",
                    workflow_kind="knowledge.extract",
                    status="succeeded",
                    checkpoint="completed",
                ),
                WorkflowRunRecord(
                    id=reviewer_run_id,
                    project_id=project_id,
                    idempotency_key="review-agent-review-fixture",
                    workflow_kind="knowledge.review",
                    status="running",
                    checkpoint="knowledge.review",
                ),
            ]
        )
        for value in ("NTE", "NTE", "Unsupported end date"):
            normalized = value.casefold()
            claim = KnowledgeClaimRecord(
                project_id=project_id,
                subject_entity_id=entity_id,
                extraction_run_id=extraction_run_id,
                predicate="game.alias",
                value_kind="string",
                value=value,
                normalized_value=normalized,
                value_fingerprint_sha256=sha256(normalized.encode()).hexdigest(),
                scope_fingerprint_sha256=sha256(b"scope").hexdigest(),
                confidence=0.9,
                locale="en",
                region="global",
                model_provider="ollama-local",
                model_name="qwen3.5:4b",
                prompt_version="knowledge-claim-v2",
                schema_version="knowledge-claim-v1",
            )
            session.add(claim)
            session.flush()
            claim_ids.append(claim.id)

    service = DatabaseAgentReviewService(sessions)
    summary = service.persist(
        run_id=reviewer_run_id,
        project_id=project_id,
        extraction_run_id=extraction_run_id,
        provider="ollama-local",
        model="qwen3.5:4b",
        fingerprints=(sha256(b"review").hexdigest(),),
        decisions=(
            AgentClaimDecision(
                claim_ids[0], "agent_approved", None, 90, "direct_support", "Direct quote.", ()
            ),
            AgentClaimDecision(
                claim_ids[1], "agent_approved", None, 80, "direct_support", "Direct quote.", ()
            ),
            AgentClaimDecision(
                claim_ids[2],
                "agent_approved",
                None,
                70,
                "context",
                "This is inferred from a standard duration.",
                (),
            ),
        ),
        input_tokens=10,
        output_tokens=10,
        total_tokens=20,
    )

    assert summary["counts"] == {
        "reviewed": 3,
        "agent_approved": 1,
        "agent_rejected": 2,
        "needs_human": 0,
    }
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ClaimReviewRecord)) == 0

    confirmation = service.confirm_pack(
        project_id=project_id,
        extraction_run_id=extraction_run_id,
        command_key="confirm-agent-review-fixture",
        actor_id="local-user",
    )
    assert confirmation == {"created_review_count": 3, "needs_human_count": 0}
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ClaimReviewRecord)) == 3
