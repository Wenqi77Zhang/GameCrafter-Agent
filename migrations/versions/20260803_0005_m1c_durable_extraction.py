"""Create durable extraction results and redacted model invocation traces.

Revision ID: 20260803_0005
Revises: 20260802_0004
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0005"
down_revision: str | None = "20260802_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add idempotent document results and per-attempt invocation observability."""

    op.create_table(
        "knowledge_extraction_results",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=80), nullable=False),
        sa.Column("max_chars", sa.Integer(), nullable=False),
        sa.Column("overlap_chars", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("invocation_count", sa.Integer(), nullable=False),
        sa.Column("claim_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(document_sha256) = 64 AND length(manifest_sha256) = 64",
            name="ck_knowledge_extraction_results_hashes",
        ),
        sa.CheckConstraint(
            "max_chars > 0 AND overlap_chars >= 0 AND overlap_chars < max_chars",
            name="ck_knowledge_extraction_results_chunking",
        ),
        sa.CheckConstraint(
            "invocation_count >= 0 AND claim_count >= 0",
            name="ck_knowledge_extraction_results_counts",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_knowledge_extraction_results_usage",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["source_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"],
            ["knowledge_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_knowledge_extraction_results_project_created",
        "knowledge_extraction_results",
        ["project_id", "created_at"],
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_extraction_results_immutable
        BEFORE UPDATE OR DELETE ON knowledge_extraction_results
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_knowledge_change()
        """
    )

    op.create_table(
        "model_invocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=False),
        sa.Column("job_attempt", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("response_id", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("claim_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_model_invocations_status",
        ),
        sa.CheckConstraint(
            "job_attempt > 0",
            name="ck_model_invocations_attempt_positive",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_model_invocations_chunk_nonnegative",
        ),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_model_invocations_offsets",
        ),
        sa.CheckConstraint(
            "length(chunk_id) = 64 AND length(request_fingerprint_sha256) = 64",
            name="ck_model_invocations_hashes",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens AND claim_count >= 0",
            name="ck_model_invocations_usage",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error_code IS NULL) "
            "OR (status = 'succeeded' AND finished_at IS NOT NULL "
            "AND provider IS NOT NULL AND model IS NOT NULL AND response_id IS NOT NULL "
            "AND error_code IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_model_invocations_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["source_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"],
            ["knowledge_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "job_attempt",
            "chunk_index",
            name="uq_model_invocations_run_attempt_chunk",
        ),
    )
    op.create_index(
        "ix_model_invocations_run_attempt",
        "model_invocations",
        ["run_id", "job_attempt", "chunk_index"],
    )
    op.create_index(
        "ix_model_invocations_project_started",
        "model_invocations",
        ["project_id", "started_at"],
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_extraction_lineage()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM workflow_runs
                WHERE id = NEW.run_id
                  AND project_id = NEW.project_id
                  AND workflow_kind = 'knowledge.extract'
            ) THEN
                RAISE EXCEPTION 'extraction run must stay inside its project and workflow kind';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM knowledge_entities
                WHERE id = NEW.subject_entity_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'extraction subject must stay inside its project';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM source_versions version
                JOIN sources source ON source.id = version.source_id
                WHERE version.id = NEW.source_version_id
                  AND source.project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'extraction source must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in ("knowledge_extraction_results", "model_invocations"):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_validate_lineage
            BEFORE INSERT OR UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_extraction_lineage()
            """
        )


def downgrade() -> None:
    """Remove durable extraction metadata without changing C2.3a workflow tables."""

    for table_name in ("model_invocations", "knowledge_extraction_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_validate_lineage ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_extraction_lineage")
    op.drop_index(
        "ix_model_invocations_project_started",
        table_name="model_invocations",
    )
    op.drop_index(
        "ix_model_invocations_run_attempt",
        table_name="model_invocations",
    )
    op.drop_table("model_invocations")
    op.execute(
        "DROP TRIGGER knowledge_extraction_results_immutable ON knowledge_extraction_results"
    )
    op.drop_index(
        "ix_knowledge_extraction_results_project_created",
        table_name="knowledge_extraction_results",
    )
    op.drop_table("knowledge_extraction_results")
