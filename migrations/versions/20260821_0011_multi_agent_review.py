"""Add independent Knowledge Reviewer Agent decisions.

Revision ID: 20260821_0011
Revises: 20260815_0010
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0011"
down_revision: str | None = "20260815_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "agent_review_results",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_agent_key", sa.String(80), nullable=False),
        sa.Column("reviewer_version", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("input_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_count", sa.Integer(), nullable=False),
        sa.Column("approved_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("needs_human_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reviewed_count >= 0 AND approved_count >= 0 AND rejected_count >= 0 "
            "AND needs_human_count >= 0 AND reviewed_count = approved_count "
            "+ rejected_count + needs_human_count",
            name="ck_agent_review_results_counts",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_agent_review_results_usage",
        ),
        sa.CheckConstraint(
            "length(input_fingerprint_sha256) = 64",
            name="ck_agent_review_results_fingerprint",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint(
            "project_id",
            "extraction_run_id",
            "reviewer_version",
            name="uq_agent_review_results_target_version",
        ),
    )
    op.create_index(
        "ix_agent_review_results_project_created",
        "agent_review_results",
        ["project_id", "created_at"],
    )
    op.create_table(
        "claim_agent_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_run_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("suggested_predicate", sa.String(80)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("rationale", sa.String(300), nullable=False),
        sa.Column("risk_codes", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('agent_approved', 'agent_rejected', 'needs_human')",
            name="ck_claim_agent_reviews_decision",
        ),
        sa.CheckConstraint("priority BETWEEN 0 AND 100", name="ck_claim_agent_reviews_priority"),
        sa.CheckConstraint(
            "length(trim(reason_code)) > 0 AND length(trim(rationale)) > 0",
            name="ck_claim_agent_reviews_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reviewer_run_id"], ["agent_review_results.run_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["knowledge_claims.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reviewer_run_id", "claim_id", name="uq_claim_agent_reviews_run_claim"),
    )
    op.create_index(
        "ix_claim_agent_reviews_claim_created",
        "claim_agent_reviews",
        ["claim_id", "created_at"],
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_agent_review_result()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM workflow_runs review_run
                JOIN workflow_runs extraction_run ON extraction_run.id = NEW.extraction_run_id
                JOIN knowledge_extraction_results extraction
                  ON extraction.run_id = NEW.extraction_run_id
                WHERE review_run.id = NEW.run_id
                  AND review_run.project_id = NEW.project_id
                  AND review_run.workflow_kind = 'knowledge.review'
                  AND extraction_run.project_id = NEW.project_id
                  AND extraction.project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'agent review result lineage is invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER agent_review_results_lineage BEFORE INSERT ON agent_review_results "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_agent_review_result()"
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_claim_agent_review()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM agent_review_results result
                JOIN knowledge_claims claim ON claim.id = NEW.claim_id
                WHERE result.run_id = NEW.reviewer_run_id
                  AND result.project_id = NEW.project_id
                  AND claim.project_id = NEW.project_id
                  AND claim.extraction_run_id = result.extraction_run_id
            ) THEN
                RAISE EXCEPTION 'claim agent review lineage is invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER claim_agent_reviews_lineage BEFORE INSERT ON claim_agent_reviews "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_claim_agent_review()"
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_prevent_agent_review_change()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'agent review lineage is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("agent_review_results", "claim_agent_reviews"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_agent_review_change()"
        )


def downgrade() -> None:
    for table in ("claim_agent_reviews", "agent_review_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_prevent_agent_review_change")
    op.execute("DROP TRIGGER IF EXISTS claim_agent_reviews_lineage ON claim_agent_reviews")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_claim_agent_review")
    op.execute("DROP TRIGGER IF EXISTS agent_review_results_lineage ON agent_review_results")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_agent_review_result")
    op.drop_index("ix_claim_agent_reviews_claim_created", table_name="claim_agent_reviews")
    op.drop_table("claim_agent_reviews")
    op.drop_index("ix_agent_review_results_project_created", table_name="agent_review_results")
    op.drop_table("agent_review_results")
