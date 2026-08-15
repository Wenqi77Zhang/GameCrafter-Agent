"""Add idempotent human-review and conflict-closure command lineage.

Revision ID: 20260815_0007
Revises: 20260815_0006
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0007"
down_revision: str | None = "20260815_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make retries safe and require complete human conflict-closure metadata."""

    op.add_column("claim_reviews", sa.Column("command_key", sa.String(length=160)))
    op.create_unique_constraint(
        "uq_claim_reviews_project_command_key",
        "claim_reviews",
        ["project_id", "command_key"],
    )

    op.add_column(
        "claim_conflict_groups",
        sa.Column("resolution_command_key", sa.String(length=160)),
    )
    op.add_column(
        "claim_conflict_groups",
        sa.Column("resolution_review_counts", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.execute(
        """
        UPDATE claim_conflict_groups
        SET resolution_summary = COALESCE(
                NULLIF(trim(resolution_summary), ''),
                'Legacy human closure migrated before C4 command lineage.'
            ),
            resolved_by = COALESCE(resolved_by, 'legacy-local-user'),
            resolved_at = COALESCE(resolved_at, created_at),
            resolution_command_key = 'legacy:' || id::text,
            resolution_review_counts = '{}'::jsonb
        WHERE status IN ('resolved', 'dismissed')
        """
    )
    op.create_unique_constraint(
        "uq_claim_conflict_groups_project_resolution_command_key",
        "claim_conflict_groups",
        ["project_id", "resolution_command_key"],
    )
    op.create_check_constraint(
        "ck_claim_conflict_groups_resolution_state",
        "claim_conflict_groups",
        "(status = 'open' AND resolution_summary IS NULL AND resolved_by IS NULL "
        "AND resolved_at IS NULL AND resolution_command_key IS NULL "
        "AND resolution_review_counts IS NULL) OR "
        "(status IN ('resolved', 'dismissed') AND length(trim(resolution_summary)) > 0 "
        "AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL "
        "AND resolution_command_key IS NOT NULL AND resolution_review_counts IS NOT NULL)",
    )


def downgrade() -> None:
    """Remove C4 command lineage while retaining review and resolution content."""

    op.drop_constraint(
        "ck_claim_conflict_groups_resolution_state",
        "claim_conflict_groups",
        type_="check",
    )
    op.drop_constraint(
        "uq_claim_conflict_groups_project_resolution_command_key",
        "claim_conflict_groups",
        type_="unique",
    )
    op.drop_column("claim_conflict_groups", "resolution_review_counts")
    op.drop_column("claim_conflict_groups", "resolution_command_key")
    op.drop_constraint(
        "uq_claim_reviews_project_command_key",
        "claim_reviews",
        type_="unique",
    )
    op.drop_column("claim_reviews", "command_key")
