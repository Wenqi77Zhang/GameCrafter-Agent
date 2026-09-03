"""Add privacy-preserving persistent login throttling.

Revision ID: 20260826_0017
Revises: 20260826_0016
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0017"
down_revision: str | None = "20260826_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_login_throttles",
        sa.Column("email_sha256", sa.String(length=64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("failure_count >= 0", name="ck_auth_login_throttles_count"),
        sa.CheckConstraint("length(email_sha256) = 64", name="ck_auth_login_throttles_digest"),
        sa.PrimaryKeyConstraint("email_sha256"),
    )


def downgrade() -> None:
    op.drop_table("auth_login_throttles")
