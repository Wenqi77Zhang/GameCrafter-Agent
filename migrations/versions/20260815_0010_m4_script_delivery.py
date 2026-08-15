"""Add evidence-bound script versions, evaluation, final review, and export receipts.

Revision ID: 20260815_0010
Revises: 20260815_0009
Create Date: 2026-08-15
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0010"
down_revision: str | None = "20260815_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "script_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("marketing_task_id", sa.Uuid(), nullable=False),
        sa.Column("topic_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("topic_review_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("revision_budget", sa.Integer(), nullable=False),
        sa.Column("score_threshold", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(80), nullable=False),
        sa.Column("evaluator_version", sa.String(80), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_budget BETWEEN 0 AND 5", name="ck_script_runs_budget"),
        sa.CheckConstraint("score_threshold BETWEEN 1 AND 100", name="ck_script_runs_threshold"),
        sa.CheckConstraint(
            "length(trim(generator_version)) > 0 AND length(trim(evaluator_version)) > 0 AND length(trim(created_by)) > 0",
            name="ck_script_runs_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["marketing_task_id"], ["marketing_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["topic_candidate_id"], ["topic_candidates.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["topic_review_id"], ["topic_reviews.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["knowledge_snapshot_id"], ["knowledge_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "command_key", name="uq_script_runs_project_command"),
    )
    op.create_index("ix_script_runs_project_created", "script_runs", ["project_id", "created_at"])
    op.create_table(
        "script_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid()),
        sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("content", json_type, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_script_versions_number"),
        sa.CheckConstraint(
            "origin IN ('generated', 'human_edit', 'auto_revision')",
            name="ck_script_versions_origin",
        ),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_script_versions_digest"),
        sa.CheckConstraint(
            "length(trim(created_by)) > 0", name="ck_script_versions_actor_nonblank"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["script_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["script_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "version_number", name="uq_script_versions_run_number"),
        sa.UniqueConstraint("run_id", "command_key", name="uq_script_versions_run_command"),
    )
    op.create_index("ix_script_versions_run_created", "script_versions", ["run_id", "created_at"])
    op.create_table(
        "script_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("dimensions", json_type, nullable=False),
        sa.Column("issues", json_type, nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_script_evaluations_score"),
        sa.CheckConstraint(
            "length(trim(rule_version)) > 0", name="ck_script_evaluations_rule_nonblank"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["script_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["script_version_id"], ["script_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "command_key", name="uq_script_evaluations_run_command"),
    )
    op.create_index(
        "ix_script_evaluations_version_created",
        "script_evaluations",
        ["script_version_id", "created_at"],
    )
    op.create_table(
        "script_final_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewer_id", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject')", name="ck_script_final_reviews_decision"
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0 AND length(trim(reviewer_id)) > 0",
            name="ck_script_final_reviews_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["script_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["script_version_id"], ["script_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluation_id"], ["script_evaluations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "command_key", name="uq_script_final_reviews_run_command"),
    )
    op.create_index(
        "ix_script_final_reviews_run_created", "script_final_reviews", ["run_id", "created_at"]
    )
    op.create_table(
        "script_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("final_review_id", sa.Uuid(), nullable=False),
        sa.Column("format", sa.String(24), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("format IN ('markdown', 'json')", name="ck_script_exports_format"),
        sa.CheckConstraint("length(payload_sha256) = 64", name="ck_script_exports_digest"),
        sa.ForeignKeyConstraint(["run_id"], ["script_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["script_version_id"], ["script_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["final_review_id"], ["script_final_reviews.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "command_key", name="uq_script_exports_run_command"),
    )
    op.create_index("ix_script_exports_run_created", "script_exports", ["run_id", "created_at"])
    op.execute("""
    CREATE FUNCTION gamecrafter_validate_script_run() RETURNS trigger AS $$
    DECLARE task_project uuid; task_snapshot uuid; candidate_task uuid; review_task uuid; review_candidate uuid; review_decision text;
    BEGIN
      SELECT project_id, knowledge_snapshot_id INTO task_project, task_snapshot FROM marketing_tasks WHERE id=NEW.marketing_task_id;
      SELECT task_id INTO candidate_task FROM topic_candidates WHERE id=NEW.topic_candidate_id;
      SELECT task_id, candidate_id, decision INTO review_task, review_candidate, review_decision FROM topic_reviews WHERE id=NEW.topic_review_id;
      IF task_project IS NULL OR task_project<>NEW.project_id OR task_snapshot<>NEW.knowledge_snapshot_id OR candidate_task<>NEW.marketing_task_id OR review_task<>NEW.marketing_task_id OR review_candidate<>NEW.topic_candidate_id OR review_decision<>'approve' THEN
        RAISE EXCEPTION 'script run lineage must bind one approved topic and snapshot'; END IF; RETURN NEW;
    END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER script_runs_lineage BEFORE INSERT ON script_runs FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_script_run()"
    )
    op.execute("""
    CREATE FUNCTION gamecrafter_validate_script_child() RETURNS trigger AS $$
    DECLARE row_data jsonb := to_jsonb(NEW); parent_run uuid; version_run uuid; evaluation_run uuid; evaluation_version uuid; evaluation_passed boolean; review_run uuid; review_version uuid; review_decision text;
    BEGIN
      IF TG_TABLE_NAME='script_versions' AND row_data->>'parent_version_id' IS NOT NULL THEN SELECT run_id INTO parent_run FROM script_versions WHERE id=(row_data->>'parent_version_id')::uuid; IF parent_run<>(row_data->>'run_id')::uuid THEN RAISE EXCEPTION 'script version parent must belong to run'; END IF;
      ELSIF TG_TABLE_NAME='script_evaluations' THEN SELECT run_id INTO version_run FROM script_versions WHERE id=(row_data->>'script_version_id')::uuid; IF version_run<>(row_data->>'run_id')::uuid THEN RAISE EXCEPTION 'script evaluation version must belong to run'; END IF;
      ELSIF TG_TABLE_NAME='script_final_reviews' THEN SELECT run_id INTO version_run FROM script_versions WHERE id=(row_data->>'script_version_id')::uuid; SELECT run_id,script_version_id,passed INTO evaluation_run,evaluation_version,evaluation_passed FROM script_evaluations WHERE id=(row_data->>'evaluation_id')::uuid; IF version_run<>(row_data->>'run_id')::uuid OR evaluation_run<>(row_data->>'run_id')::uuid OR evaluation_version<>(row_data->>'script_version_id')::uuid OR (row_data->>'decision'='approve' AND NOT evaluation_passed) THEN RAISE EXCEPTION 'final review must bind a passing evaluation of the same version'; END IF;
      ELSIF TG_TABLE_NAME='script_exports' THEN SELECT run_id INTO version_run FROM script_versions WHERE id=(row_data->>'script_version_id')::uuid; SELECT run_id,script_version_id,decision INTO review_run,review_version,review_decision FROM script_final_reviews WHERE id=(row_data->>'final_review_id')::uuid; IF version_run<>(row_data->>'run_id')::uuid OR review_run<>(row_data->>'run_id')::uuid OR review_version<>(row_data->>'script_version_id')::uuid OR review_decision<>'approve' THEN RAISE EXCEPTION 'export must bind final approval of the same version'; END IF; END IF; RETURN NEW;
    END; $$ LANGUAGE plpgsql
    """)
    for table in (
        "script_versions",
        "script_evaluations",
        "script_final_reviews",
        "script_exports",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_lineage BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_script_child()"
        )
    op.execute(
        """CREATE FUNCTION gamecrafter_prevent_script_change() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'script workflow records are immutable'; END; $$ LANGUAGE plpgsql"""
    )
    for table in (
        "script_runs",
        "script_versions",
        "script_evaluations",
        "script_final_reviews",
        "script_exports",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_script_change()"
        )


def downgrade() -> None:
    for table in (
        "script_exports",
        "script_final_reviews",
        "script_evaluations",
        "script_versions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_lineage ON {table}")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_script_child")
    op.execute("DROP TRIGGER IF EXISTS script_runs_lineage ON script_runs")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_script_run")
    for table in (
        "script_exports",
        "script_final_reviews",
        "script_evaluations",
        "script_versions",
        "script_runs",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_prevent_script_change")
    for table, index in (
        ("script_exports", "ix_script_exports_run_created"),
        ("script_final_reviews", "ix_script_final_reviews_run_created"),
        ("script_evaluations", "ix_script_evaluations_version_created"),
        ("script_versions", "ix_script_versions_run_created"),
        ("script_runs", "ix_script_runs_project_created"),
    ):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
