"""Add append-only account and team security audit events.

Revision ID: 20260826_0016
Revises: 20260826_0015
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0016"
down_revision: str | None = "20260826_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_audit_actor_created",
        "security_audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_security_audit_team_created",
        "security_audit_events",
        ["team_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_audit_team_created", table_name="security_audit_events")
    op.drop_index("ix_security_audit_actor_created", table_name="security_audit_events")
    op.drop_table("security_audit_events")
