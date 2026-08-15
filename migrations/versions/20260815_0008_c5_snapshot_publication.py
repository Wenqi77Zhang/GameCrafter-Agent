"""Add versioned idempotent knowledge-snapshot publication metadata.

Revision ID: 20260815_0008
Revises: 20260815_0007
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0008"
down_revision: str | None = "20260815_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Version snapshot payloads and make publication retries idempotent."""

    op.add_column(
        "knowledge_snapshots",
        sa.Column(
            "schema_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-snapshot-v0",
        ),
    )
    op.add_column("knowledge_snapshots", sa.Column("command_key", sa.String(length=160)))
    op.create_unique_constraint(
        "uq_knowledge_snapshots_project_command_key",
        "knowledge_snapshots",
        ["project_id", "command_key"],
    )
    op.add_column(
        "knowledge_snapshot_members",
        sa.Column("entity_revision_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_knowledge_snapshot_members_entity_revision",
        "knowledge_snapshot_members",
        "knowledge_entity_revisions",
        ["entity_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_knowledge_snapshot_members_entity_revision",
        "knowledge_snapshot_members",
        ["entity_revision_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION gamecrafter_validate_snapshot_member()
        RETURNS trigger AS $$
        DECLARE
            snapshot_project uuid;
            claim_project uuid;
            claim_entity uuid;
            review_project uuid;
            review_claim uuid;
            review_decision text;
            revision_project uuid;
            revision_entity uuid;
        BEGIN
            SELECT project_id INTO snapshot_project
            FROM knowledge_snapshots WHERE id = NEW.snapshot_id;
            SELECT project_id, subject_entity_id INTO claim_project, claim_entity
            FROM knowledge_claims WHERE id = NEW.claim_id;
            SELECT project_id, claim_id, decision
            INTO review_project, review_claim, review_decision
            FROM claim_reviews WHERE id = NEW.review_id;
            SELECT project_id, entity_id INTO revision_project, revision_entity
            FROM knowledge_entity_revisions WHERE id = NEW.entity_revision_id;

            IF snapshot_project IS NULL
               OR snapshot_project <> claim_project
               OR snapshot_project <> review_project
               OR review_claim <> NEW.claim_id THEN
                RAISE EXCEPTION 'snapshot member lineage must stay inside one project and claim';
            END IF;
            IF NEW.entity_revision_id IS NULL
               OR revision_project IS NULL
               OR revision_project <> snapshot_project
               OR revision_entity <> claim_entity THEN
                RAISE EXCEPTION 'snapshot member entity revision must match the claim subject';
            END IF;
            IF review_decision NOT IN ('approve', 'approve_with_edit') THEN
                RAISE EXCEPTION 'snapshot member requires an approving review';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM claim_evidence_spans WHERE claim_id = NEW.claim_id
            ) THEN
                RAISE EXCEPTION 'snapshot member requires claim evidence';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_conflict_members member
                JOIN claim_conflict_groups conflict
                  ON conflict.id = member.conflict_group_id
                WHERE member.claim_id = NEW.claim_id
                  AND conflict.status = 'open'
            ) THEN
                RAISE EXCEPTION 'unresolved claim conflict blocks snapshot publication';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.alter_column("knowledge_snapshots", "schema_version", server_default=None)


def downgrade() -> None:
    """Remove C5 command metadata without deleting immutable snapshots."""

    op.execute(
        """
        CREATE OR REPLACE FUNCTION gamecrafter_validate_snapshot_member()
        RETURNS trigger AS $$
        DECLARE
            snapshot_project uuid;
            claim_project uuid;
            review_project uuid;
            review_claim uuid;
            review_decision text;
        BEGIN
            SELECT project_id INTO snapshot_project
            FROM knowledge_snapshots WHERE id = NEW.snapshot_id;
            SELECT project_id INTO claim_project
            FROM knowledge_claims WHERE id = NEW.claim_id;
            SELECT project_id, claim_id, decision
            INTO review_project, review_claim, review_decision
            FROM claim_reviews WHERE id = NEW.review_id;

            IF snapshot_project IS NULL
               OR snapshot_project <> claim_project
               OR snapshot_project <> review_project
               OR review_claim <> NEW.claim_id THEN
                RAISE EXCEPTION 'snapshot member lineage must stay inside one project and claim';
            END IF;
            IF review_decision NOT IN ('approve', 'approve_with_edit') THEN
                RAISE EXCEPTION 'snapshot member requires an approving review';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM claim_evidence_spans WHERE claim_id = NEW.claim_id
            ) THEN
                RAISE EXCEPTION 'snapshot member requires claim evidence';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_conflict_members member
                JOIN claim_conflict_groups conflict
                  ON conflict.id = member.conflict_group_id
                WHERE member.claim_id = NEW.claim_id
                  AND conflict.status = 'open'
            ) THEN
                RAISE EXCEPTION 'unresolved claim conflict blocks snapshot publication';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.drop_index(
        "ix_knowledge_snapshot_members_entity_revision",
        table_name="knowledge_snapshot_members",
    )
    op.drop_constraint(
        "fk_knowledge_snapshot_members_entity_revision",
        "knowledge_snapshot_members",
        type_="foreignkey",
    )
    op.drop_column("knowledge_snapshot_members", "entity_revision_id")
    op.drop_constraint(
        "uq_knowledge_snapshots_project_command_key",
        "knowledge_snapshots",
        type_="unique",
    )
    op.drop_column("knowledge_snapshots", "command_key")
    op.drop_column("knowledge_snapshots", "schema_version")
