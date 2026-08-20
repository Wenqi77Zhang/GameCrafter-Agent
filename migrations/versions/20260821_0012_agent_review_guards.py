"""Install reviewer lineage and append-only guards for upgraded databases.

Revision ID: 20260821_0012
Revises: 20260821_0011
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260821_0012"
down_revision: str | None = "20260821_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("claim_agent_reviews", "agent_review_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP TRIGGER IF EXISTS claim_agent_reviews_lineage ON claim_agent_reviews")
    op.execute("DROP TRIGGER IF EXISTS agent_review_results_lineage ON agent_review_results")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION gamecrafter_validate_agent_review_result()
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
        """
        CREATE OR REPLACE FUNCTION gamecrafter_validate_claim_agent_review()
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
        """
        CREATE OR REPLACE FUNCTION gamecrafter_prevent_agent_review_change()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'agent review lineage is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER agent_review_results_lineage BEFORE INSERT ON agent_review_results "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_agent_review_result()"
    )
    op.execute(
        "CREATE TRIGGER claim_agent_reviews_lineage BEFORE INSERT ON claim_agent_reviews "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_claim_agent_review()"
    )
    for table in ("agent_review_results", "claim_agent_reviews"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_agent_review_change()"
        )


def downgrade() -> None:
    for table in ("claim_agent_reviews", "agent_review_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP TRIGGER IF EXISTS claim_agent_reviews_lineage ON claim_agent_reviews")
    op.execute("DROP TRIGGER IF EXISTS agent_review_results_lineage ON agent_review_results")
