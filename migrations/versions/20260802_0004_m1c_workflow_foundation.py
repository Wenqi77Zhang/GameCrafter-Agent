"""Generalize ingestion runs and jobs into reusable workflow infrastructure.

Revision ID: 20260802_0004
Revises: 20260729_0003
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0004"
down_revision: str | None = "20260729_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_knowledge_claim_validator(run_table: str) -> None:
    """Keep the PL/pgSQL validator aligned with the renamed run table."""

    if run_table not in {"workflow_runs", "ingestion_runs"}:
        raise ValueError("unsupported run table")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION gamecrafter_validate_knowledge_claim()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM knowledge_entities
                WHERE id = NEW.subject_entity_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'claim subject must stay inside its project';
            END IF;
            IF NEW.extraction_run_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM {run_table}
                WHERE id = NEW.extraction_run_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'claim extraction run must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )


def upgrade() -> None:
    """Rename the queue substrate without replacing tables or losing lineage."""

    op.rename_table("ingestion_runs", "workflow_runs")
    op.rename_table("ingestion_jobs", "workflow_jobs")

    for old_name, new_name in (
        ("ingestion_runs_pkey", "workflow_runs_pkey"),
        ("ingestion_runs_project_id_fkey", "workflow_runs_project_id_fkey"),
        ("ck_ingestion_runs_status", "ck_workflow_runs_status"),
        (
            "uq_ingestion_runs_project_idempotency",
            "uq_workflow_runs_project_idempotency",
        ),
    ):
        op.execute(f"ALTER TABLE workflow_runs RENAME CONSTRAINT {old_name} TO {new_name}")
    for old_name, new_name in (
        ("ingestion_jobs_pkey", "workflow_jobs_pkey"),
        ("ingestion_jobs_run_id_fkey", "workflow_jobs_run_id_fkey"),
        ("ck_ingestion_jobs_status", "ck_workflow_jobs_status"),
        (
            "ck_ingestion_jobs_attempts_nonnegative",
            "ck_workflow_jobs_attempts_nonnegative",
        ),
        (
            "ck_ingestion_jobs_max_attempts_positive",
            "ck_workflow_jobs_max_attempts_positive",
        ),
    ):
        op.execute(f"ALTER TABLE workflow_jobs RENAME CONSTRAINT {old_name} TO {new_name}")

    op.execute(
        "ALTER INDEX ix_ingestion_runs_project_created RENAME TO ix_workflow_runs_project_created"
    )
    op.execute("ALTER INDEX ix_ingestion_jobs_claimable RENAME TO ix_workflow_jobs_claimable")

    op.add_column(
        "workflow_runs",
        sa.Column("workflow_kind", sa.String(length=80), nullable=True),
    )
    op.execute(
        """
        UPDATE workflow_runs AS run
        SET workflow_kind = COALESCE(
            (
                SELECT job.task_type
                FROM workflow_jobs AS job
                WHERE job.run_id = run.id
                ORDER BY job.created_at, job.id
                LIMIT 1
            ),
            'system.unknown'
        )
        """
    )
    op.alter_column("workflow_runs", "workflow_kind", nullable=False)
    op.create_check_constraint(
        "ck_workflow_runs_kind_nonblank",
        "workflow_runs",
        "length(trim(workflow_kind)) > 0",
    )
    op.create_index(
        "ix_workflow_runs_project_kind_created",
        "workflow_runs",
        ["project_id", "workflow_kind", "created_at"],
    )
    _replace_knowledge_claim_validator("workflow_runs")


def downgrade() -> None:
    """Restore the legacy ingestion names while preserving all existing rows."""

    op.drop_index(
        "ix_workflow_runs_project_kind_created",
        table_name="workflow_runs",
    )
    op.drop_constraint(
        "ck_workflow_runs_kind_nonblank",
        "workflow_runs",
        type_="check",
    )
    op.drop_column("workflow_runs", "workflow_kind")

    op.execute("ALTER INDEX ix_workflow_jobs_claimable RENAME TO ix_ingestion_jobs_claimable")
    op.execute(
        "ALTER INDEX ix_workflow_runs_project_created RENAME TO ix_ingestion_runs_project_created"
    )
    for old_name, new_name in (
        ("workflow_jobs_pkey", "ingestion_jobs_pkey"),
        ("workflow_jobs_run_id_fkey", "ingestion_jobs_run_id_fkey"),
        ("ck_workflow_jobs_status", "ck_ingestion_jobs_status"),
        (
            "ck_workflow_jobs_attempts_nonnegative",
            "ck_ingestion_jobs_attempts_nonnegative",
        ),
        (
            "ck_workflow_jobs_max_attempts_positive",
            "ck_ingestion_jobs_max_attempts_positive",
        ),
    ):
        op.execute(f"ALTER TABLE workflow_jobs RENAME CONSTRAINT {old_name} TO {new_name}")
    for old_name, new_name in (
        ("workflow_runs_pkey", "ingestion_runs_pkey"),
        ("workflow_runs_project_id_fkey", "ingestion_runs_project_id_fkey"),
        ("ck_workflow_runs_status", "ck_ingestion_runs_status"),
        (
            "uq_workflow_runs_project_idempotency",
            "uq_ingestion_runs_project_idempotency",
        ),
    ):
        op.execute(f"ALTER TABLE workflow_runs RENAME CONSTRAINT {old_name} TO {new_name}")

    op.rename_table("workflow_jobs", "ingestion_jobs")
    op.rename_table("workflow_runs", "ingestion_runs")
    _replace_knowledge_claim_validator("ingestion_runs")
