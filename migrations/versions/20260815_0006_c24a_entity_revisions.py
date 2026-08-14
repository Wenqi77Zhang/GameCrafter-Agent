"""Add append-only corrections for stable knowledge entities.

Revision ID: 20260815_0006
Revises: 20260803_0005
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0006"
down_revision: str | None = "20260803_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve entity identity while making human-entered labels correctable."""

    op.create_table(
        "knowledge_entity_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="active",
        ),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_knowledge_entity_revisions_number_positive",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_knowledge_entity_revisions_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(aliases) = 'array'",
            name="ck_knowledge_entity_revisions_aliases_array",
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0 AND length(trim(change_reason)) > 0 "
            "AND length(trim(actor_id)) > 0",
            name="ck_knowledge_entity_revisions_text_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["knowledge_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "revision_number",
            name="uq_knowledge_entity_revisions_entity_number",
        ),
    )
    op.create_index(
        "ix_knowledge_entity_revisions_project_created",
        "knowledge_entity_revisions",
        ["project_id", "created_at"],
    )
    op.execute(
        """
        INSERT INTO knowledge_entity_revisions (
            id,
            entity_id,
            project_id,
            revision_number,
            display_name,
            aliases,
            status,
            change_reason,
            actor_id,
            created_at
        )
        SELECT
            id,
            id,
            project_id,
            1,
            display_name,
            aliases,
            'active',
            'baseline entity imported',
            'migration',
            created_at
        FROM knowledge_entities
        """
    )
    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_entity_revision()
        RETURNS trigger AS $$
        DECLARE
            expected_revision integer;
            latest_status text;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM knowledge_entities
                WHERE id = NEW.entity_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'entity revision must stay inside its project';
            END IF;

            SELECT
                COALESCE(MAX(revision_number), 0) + 1,
                (ARRAY_AGG(status ORDER BY revision_number DESC))[1]
            INTO expected_revision, latest_status
            FROM knowledge_entity_revisions
            WHERE entity_id = NEW.entity_id;

            IF NEW.revision_number <> expected_revision THEN
                RAISE EXCEPTION 'entity revision number must be sequential';
            END IF;
            IF latest_status = 'archived' THEN
                RAISE EXCEPTION 'archived entity cannot receive another revision';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_entity_revisions_lineage
        BEFORE INSERT ON knowledge_entity_revisions
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_entity_revision()
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_entity_revisions_immutable
        BEFORE UPDATE OR DELETE ON knowledge_entity_revisions
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_knowledge_change()
        """
    )


def downgrade() -> None:
    """Remove correction history without changing stable entity rows."""

    op.execute(
        "DROP TRIGGER IF EXISTS knowledge_entity_revisions_immutable ON knowledge_entity_revisions"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS knowledge_entity_revisions_lineage ON knowledge_entity_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS gamecrafter_validate_entity_revision")
    op.drop_index(
        "ix_knowledge_entity_revisions_project_created",
        table_name="knowledge_entity_revisions",
    )
    op.drop_table("knowledge_entity_revisions")
