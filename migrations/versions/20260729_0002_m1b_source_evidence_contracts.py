"""Create M1-B source discovery and evidence contracts.

Revision ID: 20260729_0002
Revises: 20260728_0001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_TYPES = (
    "'overview', 'character', 'world', 'gameplay', 'news', 'update', 'event', 'guide_faq', 'other'"
)


def upgrade() -> None:
    """Create source identities, immutable revisions, and object references."""

    op.create_table(
        "content_families",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("family_key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"source_type IN ({SOURCE_TYPES})",
            name="ck_content_families_source_type",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "family_key",
            name="uq_content_families_project_key",
        ),
    )
    op.create_index(
        "ix_content_families_project_created",
        "content_families",
        ["project_id", "created_at"],
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("content_family_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("site_key", sa.String(length=80), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("raw_category", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_sources_status"),
        sa.CheckConstraint(
            f"source_type IN ({SOURCE_TYPES})",
            name="ck_sources_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["content_family_id"],
            ["content_families.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "canonical_url", name="uq_sources_project_url"),
    )
    op.create_index("ix_sources_family", "sources", ["content_family_id"])
    op.create_index(
        "ix_sources_project_status_updated",
        "sources",
        ["project_id", "status", "updated_at"],
    )

    op.create_table(
        "stored_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=160), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=160), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_stored_objects_size_nonnegative",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64",
            name="ck_stored_objects_sha256_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_stored_objects_key"),
        sa.UniqueConstraint("sha256", name="uq_stored_objects_sha256"),
    )

    op.create_table(
        "source_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("previous_version_id", sa.Uuid(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_method", sa.String(length=24), nullable=False),
        sa.Column("change_kind", sa.String(length=24), nullable=False),
        sa.Column("raw_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalized_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("capture_policy_version", sa.String(length=80), nullable=False),
        sa.Column("http_etag", sa.String(length=500), nullable=True),
        sa.Column("http_last_modified", sa.String(length=200), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_source_versions_number_positive",
        ),
        sa.CheckConstraint(
            "capture_method IN ('http', 'playwright')",
            name="ck_source_versions_capture_method",
        ),
        sa.CheckConstraint(
            "change_kind IN ('initial', 'meaningful')",
            name="ck_source_versions_change_kind",
        ),
        sa.CheckConstraint(
            "length(raw_content_sha256) = 64",
            name="ck_source_versions_raw_sha256_length",
        ),
        sa.CheckConstraint(
            "length(normalized_text_sha256) = 64",
            name="ck_source_versions_text_sha256_length",
        ),
        sa.CheckConstraint(
            "length(evidence_fingerprint_sha256) = 64",
            name="ck_source_versions_evidence_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["previous_version_id"],
            ["source_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "evidence_fingerprint_sha256",
            name="uq_source_versions_source_fingerprint",
        ),
        sa.UniqueConstraint(
            "source_id",
            "version_number",
            name="uq_source_versions_source_number",
        ),
    )
    op.create_index(
        "ix_source_versions_source_fetched",
        "source_versions",
        ["source_id", "fetched_at"],
    )

    op.create_table(
        "source_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("stored_object_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "role IN ('raw_html', 'normalized_text', 'image')",
            name="ck_source_assets_role",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_source_assets_ordinal_nonnegative"),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["source_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stored_object_id"],
            ["stored_objects.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_version_id",
            "role",
            "ordinal",
            name="uq_source_assets_version_role_ordinal",
        ),
    )
    op.create_index(
        "ix_source_assets_stored_object",
        "source_assets",
        ["stored_object_id"],
    )

    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("imported_source_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("site_key", sa.String(length=80), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("raw_category", sa.String(length=120), nullable=True),
        sa.Column("family_key", sa.String(length=160), nullable=True),
        sa.Column("classification_basis", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('discovered', 'selected', 'imported', 'skipped')",
            name="ck_discovery_candidates_status",
        ),
        sa.CheckConstraint(
            f"source_type IN ({SOURCE_TYPES})",
            name="ck_discovery_candidates_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["imported_source_id"],
            ["sources.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "canonical_url",
            name="uq_discovery_candidates_run_url",
        ),
    )
    op.create_index(
        "ix_discovery_candidates_project_published",
        "discovery_candidates",
        ["project_id", "published_at"],
    )
    op.create_index(
        "ix_discovery_candidates_run_status",
        "discovery_candidates",
        ["run_id", "status"],
    )

    op.execute(
        """
        CREATE FUNCTION gamecrafter_prevent_evidence_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'captured evidence records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in ("stored_objects", "source_versions", "source_assets"):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_immutable
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION gamecrafter_prevent_evidence_update()
            """
        )


def downgrade() -> None:
    """Remove M1-B evidence contracts while preserving the M1-A foundation."""

    op.drop_index(
        "ix_discovery_candidates_run_status",
        table_name="discovery_candidates",
    )
    op.drop_index(
        "ix_discovery_candidates_project_published",
        table_name="discovery_candidates",
    )
    op.drop_table("discovery_candidates")
    op.drop_index("ix_source_assets_stored_object", table_name="source_assets")
    op.drop_table("source_assets")
    op.drop_index("ix_source_versions_source_fetched", table_name="source_versions")
    op.drop_table("source_versions")
    op.drop_table("stored_objects")
    op.drop_index("ix_sources_project_status_updated", table_name="sources")
    op.drop_index("ix_sources_family", table_name="sources")
    op.drop_table("sources")
    op.drop_index(
        "ix_content_families_project_created",
        table_name="content_families",
    )
    op.drop_table("content_families")
    op.execute("DROP FUNCTION gamecrafter_prevent_evidence_update")
