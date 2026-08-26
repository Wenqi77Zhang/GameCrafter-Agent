"""Add private local document, transcript, and GDD evidence sources.

Revision ID: 20260826_0013
Revises: 20260821_0012
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260826_0013"
down_revision: str | None = "20260821_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPES = (
    "'overview', 'character', 'world', 'gameplay', 'news', 'update', 'event', "
    "'guide_faq', 'document', 'transcript', 'gdd', 'other'"
)


def upgrade() -> None:
    for table, constraint in (
        ("content_families", "ck_content_families_source_type"),
        ("sources", "ck_sources_source_type"),
        ("discovery_candidates", "ck_discovery_candidates_source_type"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, f"source_type IN ({_SOURCE_TYPES})")
    op.drop_constraint("ck_source_versions_capture_method", "source_versions", type_="check")
    op.create_check_constraint(
        "ck_source_versions_capture_method",
        "source_versions",
        "capture_method IN ('http', 'playwright', 'local_upload')",
    )
    op.drop_constraint("ck_source_assets_role", "source_assets", type_="check")
    op.create_check_constraint(
        "ck_source_assets_role",
        "source_assets",
        "role IN ('raw_html', 'raw_document', 'normalized_text', 'image')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sources SET source_type = 'other' "
        "WHERE source_type IN ('document', 'transcript', 'gdd')"
    )
    op.execute(
        "UPDATE content_families SET source_type = 'other' "
        "WHERE source_type IN ('document', 'transcript', 'gdd')"
    )
    op.execute(
        "UPDATE discovery_candidates SET source_type = 'other' "
        "WHERE source_type IN ('document', 'transcript', 'gdd')"
    )
    op.execute("UPDATE source_assets SET role = 'raw_html' WHERE role = 'raw_document'")
    op.execute(
        "UPDATE source_versions SET capture_method = 'http' WHERE capture_method = 'local_upload'"
    )
    legacy = (
        "'overview', 'character', 'world', 'gameplay', 'news', 'update', 'event', "
        "'guide_faq', 'other'"
    )
    for table, constraint in (
        ("content_families", "ck_content_families_source_type"),
        ("sources", "ck_sources_source_type"),
        ("discovery_candidates", "ck_discovery_candidates_source_type"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, f"source_type IN ({legacy})")
    op.drop_constraint("ck_source_versions_capture_method", "source_versions", type_="check")
    op.create_check_constraint(
        "ck_source_versions_capture_method",
        "source_versions",
        "capture_method IN ('http', 'playwright')",
    )
    op.drop_constraint("ck_source_assets_role", "source_assets", type_="check")
    op.create_check_constraint(
        "ck_source_assets_role",
        "source_assets",
        "role IN ('raw_html', 'normalized_text', 'image')",
    )
