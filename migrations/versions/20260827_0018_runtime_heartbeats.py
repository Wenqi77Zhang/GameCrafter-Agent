"""Add local runtime heartbeat diagnostics.

Revision ID: 20260827_0018
Revises: 20260826_0017
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0018"
down_revision: str | None = "20260826_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_heartbeats",
        sa.Column("component_key", sa.String(length=180), nullable=False),
        sa.Column("component_type", sa.String(length=40), nullable=False),
        sa.Column("instance_id", sa.String(length=120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("component_type IN ('worker')", name="ck_runtime_heartbeats_type"),
        sa.PrimaryKeyConstraint("component_key"),
    )
    op.create_index(
        "ix_runtime_heartbeats_type_seen",
        "runtime_heartbeats",
        ["component_type", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_heartbeats_type_seen", table_name="runtime_heartbeats")
    op.drop_table("runtime_heartbeats")
