"""Create M1-C reviewable knowledge and immutable snapshot contracts.

Revision ID: 20260729_0003
Revises: 20260729_0002
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_0003"
down_revision: str | None = "20260729_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITY_TYPES = (
    "'game', 'character', 'organization', 'location', 'faction', 'platform', "
    "'gameplay_system', 'event', 'other'"
)
PREDICATES = (
    "'game.name', 'game.alias', 'game.developer', 'game.publisher', 'release.status', "
    "'release.date', 'platform.availability', 'business.model', 'genre.primary', "
    "'world.setting', 'world.location', 'faction.description', 'character.identity', "
    "'character.affiliation', 'character.ability', 'gameplay.combat', "
    "'gameplay.exploration', 'gameplay.vehicle', 'gameplay.quest', 'gameplay.multiplayer', "
    "'feature.description', 'event.schedule', 'update.change', 'unclassified'"
)
VALUE_KINDS = "'string', 'number', 'boolean', 'date', 'datetime', 'entity_ref', 'string_list'"


def json_column(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    """Create one JSONB column without repeating dialect setup."""

    arguments: dict[str, object] = {"nullable": nullable}
    if default is not None:
        arguments["server_default"] = sa.text(default)
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        **arguments,
    )


def upgrade() -> None:
    """Create entities, claims, evidence, reviews, conflicts, and snapshots."""

    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_key", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        json_column("aliases", default="'[]'::jsonb"),
        json_column("details", default="'{}'::jsonb"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"entity_type IN ({ENTITY_TYPES})",
            name="ck_knowledge_entities_type",
        ),
        sa.CheckConstraint(
            "length(trim(canonical_key)) > 0 AND length(trim(display_name)) > 0",
            name="ck_knowledge_entities_names_nonblank",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "entity_type",
            "canonical_key",
            name="uq_knowledge_entities_project_type_key",
        ),
    )
    op.create_index(
        "ix_knowledge_entities_project_type",
        "knowledge_entities",
        ["project_id", "entity_type"],
    )

    op.create_table(
        "knowledge_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=True),
        sa.Column("predicate", sa.String(length=80), nullable=False),
        sa.Column("value_kind", sa.String(length=32), nullable=False),
        json_column("value"),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("value_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("scope_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("game_version", sa.String(length=120), nullable=True),
        sa.Column("model_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"predicate IN ({PREDICATES})",
            name="ck_knowledge_claims_predicate",
        ),
        sa.CheckConstraint(
            f"value_kind IN ({VALUE_KINDS})",
            name="ck_knowledge_claims_value_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_claims_confidence",
        ),
        sa.CheckConstraint(
            "length(value_fingerprint_sha256) = 64",
            name="ck_knowledge_claims_value_fingerprint",
        ),
        sa.CheckConstraint(
            "length(scope_fingerprint_sha256) = 64",
            name="ck_knowledge_claims_scope_fingerprint",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_value)) > 0",
            name="ck_knowledge_claims_normalized_value_nonblank",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_knowledge_claims_effective_window",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["ingestion_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"],
            ["knowledge_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_claims_project_predicate",
        "knowledge_claims",
        ["project_id", "predicate"],
    )
    op.create_index(
        "ix_knowledge_claims_subject_scope",
        "knowledge_claims",
        ["subject_entity_id", "scope_fingerprint_sha256"],
    )

    op.create_table(
        "claim_evidence_spans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_claim_evidence_spans_ordinal"),
        sa.CheckConstraint("start_offset >= 0", name="ck_claim_evidence_spans_start"),
        sa.CheckConstraint(
            "end_offset > start_offset",
            name="ck_claim_evidence_spans_end",
        ),
        sa.CheckConstraint(
            "length(quote_sha256) = 64",
            name="ck_claim_evidence_spans_quote_sha256",
        ),
        sa.CheckConstraint(
            "length(trim(quote)) > 0 AND end_offset - start_offset = length(quote)",
            name="ck_claim_evidence_spans_quote_range",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["knowledge_claims.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["source_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "claim_id",
            "ordinal",
            name="uq_claim_evidence_spans_claim_ordinal",
        ),
    )
    op.create_index(
        "ix_claim_evidence_spans_source_version",
        "claim_evidence_spans",
        ["source_version_id"],
    )

    op.create_table(
        "claim_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("approved_value_kind", sa.String(length=32), nullable=True),
        json_column("approved_value", nullable=True),
        sa.Column("approved_normalized_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve', 'approve_with_edit', 'reject', 'defer')",
            name="ck_claim_reviews_decision",
        ),
        sa.CheckConstraint(
            f"approved_value_kind IS NULL OR approved_value_kind IN ({VALUE_KINDS})",
            name="ck_claim_reviews_approved_value_kind",
        ),
        sa.CheckConstraint(
            "(decision IN ('approve', 'approve_with_edit') "
            "AND approved_value IS NOT NULL AND approved_value_kind IS NOT NULL "
            "AND approved_normalized_value IS NOT NULL) "
            "OR (decision IN ('reject', 'defer') "
            "AND approved_value IS NULL AND approved_value_kind IS NULL "
            "AND approved_normalized_value IS NULL)",
            name="ck_claim_reviews_decision_value",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_claim_reviews_reason_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["knowledge_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_claim_reviews_claim_created",
        "claim_reviews",
        ["claim_id", "created_at"],
    )

    op.create_table(
        "claim_conflict_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=False),
        sa.Column("predicate", sa.String(length=80), nullable=False),
        sa.Column("scope_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"predicate IN ({PREDICATES})",
            name="ck_claim_conflict_groups_predicate",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_claim_conflict_groups_status",
        ),
        sa.CheckConstraint(
            "length(scope_fingerprint_sha256) = 64",
            name="ck_claim_conflict_groups_scope_fingerprint",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"],
            ["knowledge_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "subject_entity_id",
            "predicate",
            "scope_fingerprint_sha256",
            name="uq_claim_conflict_groups_comparison_key",
        ),
    )
    op.create_index(
        "ix_claim_conflict_groups_project_status",
        "claim_conflict_groups",
        ["project_id", "status"],
    )

    op.create_table(
        "claim_conflict_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conflict_group_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relation IN ('conflicting', 'possibly_coexisting')",
            name="ck_claim_conflict_members_relation",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["knowledge_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conflict_group_id"],
            ["claim_conflict_groups.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conflict_group_id",
            "claim_id",
            name="uq_claim_conflict_members_group_claim",
        ),
    )
    op.create_index(
        "ix_claim_conflict_members_claim",
        "claim_conflict_members",
        ["claim_id"],
    )

    op.create_table(
        "knowledge_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("published_by", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_knowledge_snapshots_version",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_knowledge_snapshots_content_sha256",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "version_number",
            name="uq_knowledge_snapshots_project_version",
        ),
    )
    op.create_index(
        "ix_knowledge_snapshots_project_published",
        "knowledge_snapshots",
        ["project_id", "published_at"],
    )

    op.create_table(
        "knowledge_snapshot_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["knowledge_claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["claim_reviews.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["knowledge_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "claim_id",
            name="uq_knowledge_snapshot_members_snapshot_claim",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "review_id",
            name="uq_knowledge_snapshot_members_snapshot_review",
        ),
    )
    op.create_index(
        "ix_knowledge_snapshot_members_claim",
        "knowledge_snapshot_members",
        ["claim_id"],
    )

    _create_review_and_snapshot_guards()


def _create_review_and_snapshot_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION gamecrafter_prevent_knowledge_change()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'published knowledge lineage is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in (
        "knowledge_entities",
        "knowledge_claims",
        "claim_evidence_spans",
        "claim_reviews",
        "knowledge_snapshots",
        "knowledge_snapshot_members",
    ):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_knowledge_change()
            """
        )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_knowledge_claim()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM knowledge_entities
                WHERE id = NEW.subject_entity_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'claim subject must stay inside its project';
            END IF;
            IF NEW.extraction_run_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM ingestion_runs
                WHERE id = NEW.extraction_run_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'claim extraction run must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_claims_validate
        BEFORE INSERT ON knowledge_claims
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_knowledge_claim()
        """
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_claim_evidence()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM knowledge_claims claim
                JOIN source_versions version ON version.id = NEW.source_version_id
                JOIN sources source ON source.id = version.source_id
                WHERE claim.id = NEW.claim_id
                  AND claim.project_id = source.project_id
            ) THEN
                RAISE EXCEPTION 'claim evidence must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_evidence_spans_validate
        BEFORE INSERT ON claim_evidence_spans
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_claim_evidence()
        """
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_conflict_group()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM knowledge_entities
                WHERE id = NEW.subject_entity_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'conflict subject must stay inside its project';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_conflict_groups_validate
        BEFORE INSERT ON claim_conflict_groups
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_conflict_group()
        """
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_conflict_member()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM claim_conflict_groups conflict
                JOIN knowledge_claims claim ON claim.id = NEW.claim_id
                WHERE conflict.id = NEW.conflict_group_id
                  AND conflict.project_id = claim.project_id
                  AND conflict.subject_entity_id = claim.subject_entity_id
                  AND conflict.predicate = claim.predicate
                  AND conflict.scope_fingerprint_sha256 = claim.scope_fingerprint_sha256
            ) THEN
                RAISE EXCEPTION 'conflict member must match project, subject, predicate, and scope';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_conflict_members_validate
        BEFORE INSERT ON claim_conflict_members
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_conflict_member()
        """
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_claim_review()
        RETURNS trigger AS $$
        DECLARE
            claim_project uuid;
        BEGIN
            SELECT project_id INTO claim_project
            FROM knowledge_claims
            WHERE id = NEW.claim_id;

            IF claim_project IS NULL OR claim_project <> NEW.project_id THEN
                RAISE EXCEPTION 'claim review must stay inside its project';
            END IF;

            IF NEW.decision IN ('approve', 'approve_with_edit')
               AND NOT EXISTS (
                   SELECT 1 FROM claim_evidence_spans WHERE claim_id = NEW.claim_id
               ) THEN
                RAISE EXCEPTION 'a claim without evidence cannot be approved';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_reviews_validate
        BEFORE INSERT ON claim_reviews
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_claim_review()
        """
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_validate_snapshot_member()
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
    op.execute(
        """
        CREATE TRIGGER knowledge_snapshot_members_validate
        BEFORE INSERT ON knowledge_snapshot_members
        FOR EACH ROW EXECUTE FUNCTION gamecrafter_validate_snapshot_member()
        """
    )


def downgrade() -> None:
    """Remove M1-C knowledge contracts while preserving source evidence."""

    op.execute("DROP TRIGGER knowledge_snapshot_members_validate ON knowledge_snapshot_members")
    op.execute("DROP FUNCTION gamecrafter_validate_snapshot_member")
    op.execute("DROP TRIGGER claim_reviews_validate ON claim_reviews")
    op.execute("DROP FUNCTION gamecrafter_validate_claim_review")
    op.execute("DROP TRIGGER claim_conflict_members_validate ON claim_conflict_members")
    op.execute("DROP FUNCTION gamecrafter_validate_conflict_member")
    op.execute("DROP TRIGGER claim_conflict_groups_validate ON claim_conflict_groups")
    op.execute("DROP FUNCTION gamecrafter_validate_conflict_group")
    op.execute("DROP TRIGGER claim_evidence_spans_validate ON claim_evidence_spans")
    op.execute("DROP FUNCTION gamecrafter_validate_claim_evidence")
    op.execute("DROP TRIGGER knowledge_claims_validate ON knowledge_claims")
    op.execute("DROP FUNCTION gamecrafter_validate_knowledge_claim")
    for table_name in (
        "knowledge_snapshot_members",
        "knowledge_snapshots",
        "claim_reviews",
        "claim_evidence_spans",
        "knowledge_claims",
        "knowledge_entities",
    ):
        op.execute(f"DROP TRIGGER {table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION gamecrafter_prevent_knowledge_change")

    op.drop_index(
        "ix_knowledge_snapshot_members_claim",
        table_name="knowledge_snapshot_members",
    )
    op.drop_table("knowledge_snapshot_members")
    op.drop_index(
        "ix_knowledge_snapshots_project_published",
        table_name="knowledge_snapshots",
    )
    op.drop_table("knowledge_snapshots")
    op.drop_index(
        "ix_claim_conflict_members_claim",
        table_name="claim_conflict_members",
    )
    op.drop_table("claim_conflict_members")
    op.drop_index(
        "ix_claim_conflict_groups_project_status",
        table_name="claim_conflict_groups",
    )
    op.drop_table("claim_conflict_groups")
    op.drop_index("ix_claim_reviews_claim_created", table_name="claim_reviews")
    op.drop_table("claim_reviews")
    op.drop_index(
        "ix_claim_evidence_spans_source_version",
        table_name="claim_evidence_spans",
    )
    op.drop_table("claim_evidence_spans")
    op.drop_index("ix_knowledge_claims_subject_scope", table_name="knowledge_claims")
    op.drop_index("ix_knowledge_claims_project_predicate", table_name="knowledge_claims")
    op.drop_table("knowledge_claims")
    op.drop_index(
        "ix_knowledge_entities_project_type",
        table_name="knowledge_entities",
    )
    op.drop_table("knowledge_entities")
