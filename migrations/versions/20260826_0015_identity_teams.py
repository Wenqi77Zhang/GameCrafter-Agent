"""Add local accounts, revocable sessions, teams, RBAC, and project tenancy.

Revision ID: 20260826_0015
Revises: 20260826_0014
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0015"
down_revision: str | None = "20260826_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_teams_slug"),
    )
    op.add_column("projects", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column("projects", sa.Column("team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_projects_owner_user",
        "projects",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_projects_team", "projects", "teams", ["team_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_projects_owner_user", "projects", ["owner_user_id"])
    op.create_index("ix_projects_team", "projects", ["team_id"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(token_sha256) = 64", name="ck_user_sessions_digest"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256", name="uq_user_sessions_digest"),
    )
    op.create_index("ix_user_sessions_user_expiry", "user_sessions", ["user_id", "expires_at"])
    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'reviewer', 'viewer')",
            name="ck_team_memberships_role",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_team_memberships_status"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_memberships_user"),
    )
    op.create_index("ix_team_memberships_user_status", "team_memberships", ["user_id", "status"])
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('editor', 'reviewer', 'viewer')", name="ck_team_invitations_role"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_team_invitations_status",
        ),
        sa.CheckConstraint("length(token_sha256) = 64", name="ck_team_invitations_digest"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256", name="uq_team_invitations_digest"),
    )
    op.create_index("ix_team_invitations_team_status", "team_invitations", ["team_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_team_invitations_team_status", table_name="team_invitations")
    op.drop_table("team_invitations")
    op.drop_index("ix_team_memberships_user_status", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_index("ix_user_sessions_user_expiry", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_projects_team", table_name="projects")
    op.drop_index("ix_projects_owner_user", table_name="projects")
    op.drop_constraint("fk_projects_team", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_owner_user", "projects", type_="foreignkey")
    op.drop_column("projects", "team_id")
    op.drop_column("projects", "owner_user_id")
    op.drop_table("teams")
    op.drop_table("users")
