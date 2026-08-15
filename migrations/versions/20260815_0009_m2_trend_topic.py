"""Add zero-cost trend observations, fit candidates, and human topic approval.

Revision ID: 20260815_0009
Revises: 20260815_0008
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0009"
down_revision: str | None = "20260815_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "marketing_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(80), nullable=False),
        sa.Column("markets", json_type, nullable=False),
        sa.Column("audience", sa.String(500), nullable=False),
        sa.Column("goal", sa.String(500), nullable=False),
        sa.Column("output_language", sa.String(40), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "duration_seconds BETWEEN 5 AND 180", name="ck_marketing_tasks_duration"
        ),
        sa.CheckConstraint(
            "length(trim(platform)) > 0 AND length(trim(audience)) > 0 "
            "AND length(trim(goal)) > 0 AND length(trim(output_language)) > 0 "
            "AND length(trim(created_by)) > 0",
            name="ck_marketing_tasks_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["knowledge_snapshot_id"], ["knowledge_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "command_key", name="uq_marketing_tasks_project_command"),
    )
    op.create_index(
        "ix_marketing_tasks_project_created", "marketing_tasks", ["project_id", "created_at"]
    )
    op.create_table(
        "trend_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("signal_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("keywords", json_type, nullable=False),
        sa.Column("metric_name", sa.String(120)),
        sa.Column("metric_value", sa.Numeric(20, 4)),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "signal_type IN ('hashtag', 'sound', 'topic', 'search')", name="ck_trend_signals_type"
        ),
        sa.CheckConstraint(
            "metric_value IS NULL OR metric_value >= 0", name="ck_trend_signals_metric_nonnegative"
        ),
        sa.CheckConstraint(
            "length(trim(source_name)) > 0 AND length(trim(source_url)) > 0 "
            "AND length(trim(region)) > 0 AND length(trim(title)) > 0 "
            "AND length(trim(created_by)) > 0",
            name="ck_trend_signals_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "command_key", name="uq_trend_signals_project_command"),
    )
    op.create_index(
        "ix_trend_signals_project_observed", "trend_signals", ["project_id", "observed_at"]
    )
    op.create_table(
        "topic_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("trend_signal_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("dimensions", json_type, nullable=False),
        sa.Column("matched_snapshot_member_ids", json_type, nullable=False),
        sa.Column("angle", sa.String(500), nullable=False),
        sa.Column("hook", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("risks", json_type, nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_topic_candidates_score"),
        sa.CheckConstraint(
            "length(trim(angle)) > 0 AND length(trim(hook)) > 0 "
            "AND length(trim(rationale)) > 0 AND length(trim(rule_version)) > 0",
            name="ck_topic_candidates_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["marketing_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trend_signal_id"], ["trend_signals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "trend_signal_id", name="uq_topic_candidates_task_signal"),
    )
    op.create_index("ix_topic_candidates_task_score", "topic_candidates", ["task_id", "score"])
    op.create_table(
        "topic_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewer_id", sa.String(120), nullable=False),
        sa.Column("command_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'defer')", name="ck_topic_reviews_decision"
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0 AND length(trim(reviewer_id)) > 0",
            name="ck_topic_reviews_text_nonblank",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["marketing_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_id"], ["topic_candidates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "command_key", name="uq_topic_reviews_task_command"),
    )
    op.create_index("ix_topic_reviews_task_created", "topic_reviews", ["task_id", "created_at"])
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_marketing_task() RETURNS trigger AS $$
        DECLARE snapshot_project uuid;
        BEGIN
            SELECT project_id INTO snapshot_project
            FROM knowledge_snapshots WHERE id = NEW.knowledge_snapshot_id;
            IF snapshot_project IS NULL OR snapshot_project <> NEW.project_id THEN
                RAISE EXCEPTION 'marketing task snapshot must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER marketing_tasks_lineage BEFORE INSERT ON marketing_tasks "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_marketing_task()"
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_topic_candidate() RETURNS trigger AS $$
        DECLARE task_project uuid; signal_project uuid;
        BEGIN
            SELECT project_id INTO task_project FROM marketing_tasks WHERE id = NEW.task_id;
            SELECT project_id INTO signal_project FROM trend_signals WHERE id = NEW.trend_signal_id;
            IF task_project IS NULL OR signal_project IS NULL OR task_project <> signal_project THEN
                RAISE EXCEPTION 'topic candidate task and trend must stay inside one project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER topic_candidates_lineage BEFORE INSERT ON topic_candidates "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_topic_candidate()"
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_topic_review() RETURNS trigger AS $$
        DECLARE candidate_task uuid;
        BEGIN
            SELECT task_id INTO candidate_task FROM topic_candidates WHERE id = NEW.candidate_id;
            IF candidate_task IS NULL OR candidate_task <> NEW.task_id THEN
                RAISE EXCEPTION 'topic review candidate must belong to the same task';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER topic_reviews_lineage BEFORE INSERT ON topic_reviews "
        "FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_topic_review()"
    )
    op.execute("""
        CREATE FUNCTION gamecrafter_prevent_marketing_change() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'marketing evidence and decisions are immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    for table in ("marketing_tasks", "trend_signals", "topic_candidates", "topic_reviews"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_marketing_change()"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS topic_reviews_lineage ON topic_reviews")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_topic_review")
    op.execute("DROP TRIGGER IF EXISTS topic_candidates_lineage ON topic_candidates")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_topic_candidate")
    op.execute("DROP TRIGGER IF EXISTS marketing_tasks_lineage ON marketing_tasks")
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_marketing_task")
    for table in ("topic_reviews", "topic_candidates", "trend_signals", "marketing_tasks"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION gamecrafter_prevent_marketing_change")
    op.drop_index("ix_topic_reviews_task_created", table_name="topic_reviews")
    op.drop_table("topic_reviews")
    op.drop_index("ix_topic_candidates_task_score", table_name="topic_candidates")
    op.drop_table("topic_candidates")
    op.drop_index("ix_trend_signals_project_observed", table_name="trend_signals")
    op.drop_table("trend_signals")
    op.drop_index("ix_marketing_tasks_project_created", table_name="marketing_tasks")
    op.drop_table("marketing_tasks")
