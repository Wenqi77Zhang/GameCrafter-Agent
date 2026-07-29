"""SQLAlchemy records for durable runs and source evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gamecrafter.domain.runs.state import JobStatus, RunStatus


def utc_now() -> datetime:
    """Return an aware UTC timestamp for database defaults."""

    return datetime.now(UTC)


json_type = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Declarative metadata root imported by Alembic."""


class ProjectRecord(Base):
    """Single-user project boundary that can evolve into tenant isolation."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("slug", name="uq_projects_slug"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ContentFamilyRecord(Base):
    """Project-local grouping for regional or translated source variants."""

    __tablename__ = "content_families"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('overview', 'character', 'world', 'gameplay', 'news', "
            "'update', 'event', 'guide_faq', 'other')",
            name="ck_content_families_source_type",
        ),
        UniqueConstraint("project_id", "family_key", name="uq_content_families_project_key"),
        Index("ix_content_families_project_created", "project_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    family_key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str | None] = mapped_column(String(240))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SourceRecord(Base):
    """Stable identity for one project-scoped canonical official URL."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_sources_status"),
        CheckConstraint(
            "source_type IN ('overview', 'character', 'world', 'gameplay', 'news', "
            "'update', 'event', 'guide_faq', 'other')",
            name="ck_sources_source_type",
        ),
        UniqueConstraint("project_id", "canonical_url", name="uq_sources_project_url"),
        Index("ix_sources_project_status_updated", "project_id", "status", "updated_at"),
        Index("ix_sources_family", "content_family_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content_family_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("content_families.id", ondelete="SET NULL"),
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    site_key: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_category: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoredObjectRecord(Base):
    """Database metadata for one immutable content-addressed blob."""

    __tablename__ = "stored_objects"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_stored_objects_size_nonnegative"),
        CheckConstraint("length(sha256) = 64", name="ck_stored_objects_sha256_length"),
        UniqueConstraint("sha256", name="uq_stored_objects_sha256"),
        UniqueConstraint("object_key", name="uq_stored_objects_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    object_key: Mapped[str] = mapped_column(String(160), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="filesystem")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SourceVersionRecord(Base):
    """Immutable meaningful evidence revision for one source."""

    __tablename__ = "source_versions"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_source_versions_number_positive"),
        CheckConstraint(
            "capture_method IN ('http', 'playwright')",
            name="ck_source_versions_capture_method",
        ),
        CheckConstraint(
            "change_kind IN ('initial', 'meaningful')",
            name="ck_source_versions_change_kind",
        ),
        CheckConstraint(
            "length(raw_content_sha256) = 64",
            name="ck_source_versions_raw_sha256_length",
        ),
        CheckConstraint(
            "length(normalized_text_sha256) = 64",
            name="ck_source_versions_text_sha256_length",
        ),
        CheckConstraint(
            "length(evidence_fingerprint_sha256) = 64",
            name="ck_source_versions_evidence_sha256_length",
        ),
        UniqueConstraint(
            "source_id",
            "version_number",
            name="uq_source_versions_source_number",
        ),
        UniqueConstraint(
            "source_id",
            "evidence_fingerprint_sha256",
            name="uq_source_versions_source_fingerprint",
        ),
        Index("ix_source_versions_source_fetched", "source_id", "fetched_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_version_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_versions.id", ondelete="SET NULL"),
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    capture_method: Mapped[str] = mapped_column(String(24), nullable=False)
    change_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    raw_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    capture_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    http_etag: Mapped[str | None] = mapped_column(String(500))
    http_last_modified: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)


class SourceAssetRecord(Base):
    """Role and provenance of a stored object within a source version."""

    __tablename__ = "source_assets"
    __table_args__ = (
        CheckConstraint(
            "role IN ('raw_html', 'normalized_text', 'image')",
            name="ck_source_assets_role",
        ),
        CheckConstraint("ordinal >= 0", name="ck_source_assets_ordinal_nonnegative"),
        UniqueConstraint(
            "source_version_id",
            "role",
            "ordinal",
            name="uq_source_assets_version_role_ordinal",
        ),
        Index("ix_source_assets_stored_object", "stored_object_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stored_object_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stored_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_url: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)


class IngestionRunRecord(Base):
    """Durable state and checkpoint for one ingestion request."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'needs_attention', "
            "'succeeded', 'cancelled')",
            name="ck_ingestion_runs_status",
        ),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_ingestion_runs_project_idempotency",
        ),
        Index("ix_ingestion_runs_project_created", "project_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.QUEUED.value)
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscoveryCandidateRecord(Base):
    """Reviewable page metadata discovered before any full capture."""

    __tablename__ = "discovery_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered', 'selected', 'imported', 'skipped')",
            name="ck_discovery_candidates_status",
        ),
        CheckConstraint(
            "source_type IN ('overview', 'character', 'world', 'gameplay', 'news', "
            "'update', 'event', 'guide_faq', 'other')",
            name="ck_discovery_candidates_source_type",
        ),
        UniqueConstraint(
            "run_id",
            "canonical_url",
            name="uq_discovery_candidates_run_url",
        ),
        Index("ix_discovery_candidates_run_status", "run_id", "status"),
        Index("ix_discovery_candidates_project_published", "project_id", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    imported_source_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sources.id", ondelete="SET NULL"),
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    site_key: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_category: Mapped[str | None] = mapped_column(String(120))
    family_key: Mapped[str | None] = mapped_column(String(160))
    classification_basis: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="discovered")
    details: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJobRecord(Base):
    """Database-backed job with bounded attempts and an expiring lease."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'leased', 'completed', 'failed', 'cancelled')",
            name="ck_ingestion_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_ingestion_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts_positive"),
        Index("ix_ingestion_jobs_claimable", "status", "available_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=JobStatus.QUEUED.value)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AuditEventRecord(Base):
    """Append-only business event for later user-facing audit history."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('human', 'system', 'worker', 'model')",
            name="ck_audit_events_actor_type",
        ),
        Index("ix_audit_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_audit_events_run_occurred", "run_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
    )
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
