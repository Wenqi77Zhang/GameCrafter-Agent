"""Durable local creative operations and explicit model provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260910_0019"
down_revision = "20260827_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    for table, column in (
        ("script_versions", "generation_metadata"),
        ("script_evaluations", "semantic_report"),
    ):
        op.add_column(table, sa.Column(column, json_type, nullable=False, server_default="{}"))
    op.create_table(
        "creative_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(24), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("input_data", json_type, nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("stages", json_type, nullable=False),
        sa.Column("result", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_run_id", name="uq_creative_operations_workflow"),
        sa.CheckConstraint(
            "operation IN ('strategy', 'write', 'revise', 'critique')",
            name="ck_creative_operations_kind",
        ),
        sa.CheckConstraint("length(input_sha256) = 64", name="ck_creative_operations_digest"),
    )
    op.create_index(
        "ix_creative_operations_project_target",
        "creative_operations",
        ["project_id", "target_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("creative_operations")
    op.drop_column("script_evaluations", "semantic_report")
    op.drop_column("script_versions", "generation_metadata")
