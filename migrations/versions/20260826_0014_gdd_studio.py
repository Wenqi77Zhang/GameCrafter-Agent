"""Add source-bound structured GDD Studio records.

Revision ID: 20260826_0014
Revises: 20260826_0013
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0014"
down_revision: str | None = "20260826_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gdd_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_gdd_documents_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_version_id"], ["source_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "source_version_id", name="uq_gdd_project_source_version"
        ),
    )
    op.create_index(
        "ix_gdd_documents_project_created", "gdd_documents", ["project_id", "created_at"]
    )
    op.create_table(
        "gdd_chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("parent_chapter_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint("heading_level BETWEEN 1 AND 6", name="ck_gdd_chapters_level"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_gdd_chapters_offsets"
        ),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_gdd_chapters_digest"),
        sa.ForeignKeyConstraint(["document_id"], ["gdd_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_chapter_id"], ["gdd_chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_gdd_chapters_document_ordinal"),
    )
    op.create_index("ix_gdd_chapters_document_ordinal", "gdd_chapters", ["document_id", "ordinal"])
    op.create_table(
        "gdd_assumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=True),
        sa.Column("statement", sa.String(length=2000), nullable=False),
        sa.Column("rationale", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decision_reason", sa.String(length=1000), nullable=True),
        sa.Column("command_key", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name="ck_gdd_assumptions_status",
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["gdd_chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["gdd_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "command_key", name="uq_gdd_assumptions_command"),
    )
    op.create_index(
        "ix_gdd_assumptions_document_created", "gdd_assumptions", ["document_id", "created_at"]
    )
    op.create_table(
        "gdd_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("command_key", sa.String(length=160), nullable=False),
        sa.Column("approved_by", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_number > 0", name="ck_gdd_revisions_number"),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_gdd_revisions_digest"),
        sa.ForeignKeyConstraint(["document_id"], ["gdd_documents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "command_key", name="uq_gdd_revisions_command"),
        sa.UniqueConstraint("document_id", "revision_number", name="uq_gdd_revisions_number"),
    )


def downgrade() -> None:
    op.drop_table("gdd_revisions")
    op.drop_index("ix_gdd_assumptions_document_created", table_name="gdd_assumptions")
    op.drop_table("gdd_assumptions")
    op.drop_index("ix_gdd_chapters_document_ordinal", table_name="gdd_chapters")
    op.drop_table("gdd_chapters")
    op.drop_index("ix_gdd_documents_project_created", table_name="gdd_documents")
    op.drop_table("gdd_documents")
