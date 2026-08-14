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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gamecrafter.domain.knowledge.claims import (
    ClaimValueKind,
    ConflictRelation,
    ConflictStatus,
    EntityType,
    FactPredicate,
    ReviewDecision,
)
from gamecrafter.domain.runs.state import JobStatus, RunStatus


def utc_now() -> datetime:
    """Return an aware UTC timestamp for database defaults."""

    return datetime.now(UTC)


json_type = JSON().with_variant(JSONB(), "postgresql")
nullable_json_type = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


def sql_values(values: Any) -> str:
    """Return a stable quoted list for database check constraints."""

    return ", ".join(f"'{item.value}'" for item in values)


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


class WorkflowRunRecord(Base):
    """Durable state and checkpoint for one bounded workflow."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'needs_attention', "
            "'succeeded', 'cancelled')",
            name="ck_workflow_runs_status",
        ),
        CheckConstraint(
            "length(trim(workflow_kind)) > 0",
            name="ck_workflow_runs_kind_nonblank",
        ),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_workflow_runs_project_idempotency",
        ),
        Index("ix_workflow_runs_project_created", "project_id", "created_at"),
        Index(
            "ix_workflow_runs_project_kind_created",
            "project_id",
            "workflow_kind",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    workflow_kind: Mapped[str] = mapped_column(String(80), nullable=False)
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
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
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


class WorkflowJobRecord(Base):
    """Database-backed job with bounded attempts and an expiring lease."""

    __tablename__ = "workflow_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'leased', 'completed', 'failed', 'cancelled')",
            name="ck_workflow_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_workflow_jobs_attempts_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_workflow_jobs_max_attempts_positive"),
        Index("ix_workflow_jobs_claimable", "status", "available_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
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
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class KnowledgeExtractionResultRecord(Base):
    """Immutable whole-document extraction result used as the idempotency marker."""

    __tablename__ = "knowledge_extraction_results"
    __table_args__ = (
        CheckConstraint(
            "length(document_sha256) = 64 AND length(manifest_sha256) = 64",
            name="ck_knowledge_extraction_results_hashes",
        ),
        CheckConstraint(
            "max_chars > 0 AND overlap_chars >= 0 AND overlap_chars < max_chars",
            name="ck_knowledge_extraction_results_chunking",
        ),
        CheckConstraint(
            "invocation_count >= 0 AND claim_count >= 0",
            name="ck_knowledge_extraction_results_counts",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_knowledge_extraction_results_usage",
        ),
        Index(
            "ix_knowledge_extraction_results_project_created",
            "project_id",
            "created_at",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(80), nullable=False)
    max_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    overlap_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    invocation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ModelInvocationRecord(Base):
    """Redacted per-chunk model lifecycle metadata for one durable job attempt."""

    __tablename__ = "model_invocations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_model_invocations_status",
        ),
        CheckConstraint("job_attempt > 0", name="ck_model_invocations_attempt_positive"),
        CheckConstraint("chunk_index >= 0", name="ck_model_invocations_chunk_nonnegative"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_model_invocations_offsets",
        ),
        CheckConstraint(
            "length(chunk_id) = 64 AND length(request_fingerprint_sha256) = 64",
            name="ck_model_invocations_hashes",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens AND claim_count >= 0",
            name="ck_model_invocations_usage",
        ),
        CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error_code IS NULL) "
            "OR (status = 'succeeded' AND finished_at IS NOT NULL "
            "AND provider IS NOT NULL AND model IS NOT NULL AND response_id IS NOT NULL "
            "AND error_code IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL AND error_code IS NOT NULL)",
            name="ck_model_invocations_outcome",
        ),
        UniqueConstraint(
            "run_id",
            "job_attempt",
            "chunk_index",
            name="uq_model_invocations_run_attempt_chunk",
        ),
        Index("ix_model_invocations_run_attempt", "run_id", "job_attempt", "chunk_index"),
        Index("ix_model_invocations_project_started", "project_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    request_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    response_id: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeEntityRecord(Base):
    """Project-local subject identity used by reviewable claims."""

    __tablename__ = "knowledge_entities"
    __table_args__ = (
        CheckConstraint(
            f"entity_type IN ({sql_values(EntityType)})",
            name="ck_knowledge_entities_type",
        ),
        CheckConstraint(
            "length(trim(canonical_key)) > 0 AND length(trim(display_name)) > 0",
            name="ck_knowledge_entities_names_nonblank",
        ),
        UniqueConstraint(
            "project_id",
            "entity_type",
            "canonical_key",
            name="uq_knowledge_entities_project_type_key",
        ),
        Index("ix_knowledge_entities_project_type", "project_id", "entity_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(json_type, nullable=False, default=list)
    details: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class KnowledgeEntityRevisionRecord(Base):
    """Append-only user correction or archival state for one stable entity."""

    __tablename__ = "knowledge_entity_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_knowledge_entity_revisions_number_positive",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_knowledge_entity_revisions_status",
        ),
        CheckConstraint(
            "length(trim(display_name)) > 0 AND length(trim(change_reason)) > 0 "
            "AND length(trim(actor_id)) > 0",
            name="ck_knowledge_entity_revisions_text_nonblank",
        ),
        UniqueConstraint(
            "entity_id",
            "revision_number",
            name="uq_knowledge_entity_revisions_entity_number",
        ),
        Index(
            "ix_knowledge_entity_revisions_project_created",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(json_type, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class KnowledgeClaimRecord(Base):
    """Immutable model-produced claim awaiting an append-only human decision."""

    __tablename__ = "knowledge_claims"
    __table_args__ = (
        CheckConstraint(
            f"predicate IN ({sql_values(FactPredicate)})",
            name="ck_knowledge_claims_predicate",
        ),
        CheckConstraint(
            f"value_kind IN ({sql_values(ClaimValueKind)})",
            name="ck_knowledge_claims_value_kind",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_claims_confidence",
        ),
        CheckConstraint(
            "length(value_fingerprint_sha256) = 64",
            name="ck_knowledge_claims_value_fingerprint",
        ),
        CheckConstraint(
            "length(scope_fingerprint_sha256) = 64",
            name="ck_knowledge_claims_scope_fingerprint",
        ),
        CheckConstraint(
            "length(trim(normalized_value)) > 0",
            name="ck_knowledge_claims_normalized_value_nonblank",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_knowledge_claims_effective_window",
        ),
        Index("ix_knowledge_claims_project_predicate", "project_id", "predicate"),
        Index("ix_knowledge_claims_subject_scope", "subject_entity_id", "scope_fingerprint_sha256"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    extraction_run_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
    )
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    value_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[Any] = mapped_column(json_type, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    value_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_version: Mapped[str | None] = mapped_column(String(120))
    model_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ClaimEvidenceSpanRecord(Base):
    """Immutable exact evidence range supporting one candidate claim."""

    __tablename__ = "claim_evidence_spans"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_claim_evidence_spans_ordinal"),
        CheckConstraint("start_offset >= 0", name="ck_claim_evidence_spans_start"),
        CheckConstraint(
            "end_offset > start_offset",
            name="ck_claim_evidence_spans_end",
        ),
        CheckConstraint(
            "length(quote_sha256) = 64",
            name="ck_claim_evidence_spans_quote_sha256",
        ),
        CheckConstraint(
            "length(trim(quote)) > 0 AND end_offset - start_offset = length(quote)",
            name="ck_claim_evidence_spans_quote_range",
        ),
        UniqueConstraint(
            "claim_id",
            "ordinal",
            name="uq_claim_evidence_spans_claim_ordinal",
        ),
        Index("ix_claim_evidence_spans_source_version", "source_version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ClaimReviewRecord(Base):
    """Append-only human decision that may carry an approved edited value."""

    __tablename__ = "claim_reviews"
    __table_args__ = (
        CheckConstraint(
            f"decision IN ({sql_values(ReviewDecision)})",
            name="ck_claim_reviews_decision",
        ),
        CheckConstraint(
            f"approved_value_kind IS NULL OR approved_value_kind IN ({sql_values(ClaimValueKind)})",
            name="ck_claim_reviews_approved_value_kind",
        ),
        CheckConstraint(
            "("
            "decision IN ('approve', 'approve_with_edit') "
            "AND approved_value IS NOT NULL AND approved_value_kind IS NOT NULL "
            "AND approved_normalized_value IS NOT NULL"
            ") OR ("
            "decision IN ('reject', 'defer') "
            "AND approved_value IS NULL AND approved_value_kind IS NULL "
            "AND approved_normalized_value IS NULL"
            ")",
            name="ck_claim_reviews_decision_value",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_claim_reviews_reason_nonblank",
        ),
        Index("ix_claim_reviews_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_value_kind: Mapped[str | None] = mapped_column(String(32))
    approved_value: Mapped[Any | None] = mapped_column(nullable_json_type)
    approved_normalized_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ClaimConflictGroupRecord(Base):
    """Potentially conflicting claims sharing one deterministic comparison key."""

    __tablename__ = "claim_conflict_groups"
    __table_args__ = (
        CheckConstraint(
            f"predicate IN ({sql_values(FactPredicate)})",
            name="ck_claim_conflict_groups_predicate",
        ),
        CheckConstraint(
            f"status IN ({sql_values(ConflictStatus)})",
            name="ck_claim_conflict_groups_status",
        ),
        CheckConstraint(
            "length(scope_fingerprint_sha256) = 64",
            name="ck_claim_conflict_groups_scope_fingerprint",
        ),
        UniqueConstraint(
            "project_id",
            "subject_entity_id",
            "predicate",
            "scope_fingerprint_sha256",
            name="uq_claim_conflict_groups_comparison_key",
        ),
        Index("ix_claim_conflict_groups_project_status", "project_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_entity_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ClaimConflictMemberRecord(Base):
    """Membership and deterministic relation inside one conflict group."""

    __tablename__ = "claim_conflict_members"
    __table_args__ = (
        CheckConstraint(
            f"relation IN ({sql_values(ConflictRelation)})",
            name="ck_claim_conflict_members_relation",
        ),
        UniqueConstraint(
            "conflict_group_id",
            "claim_id",
            name="uq_claim_conflict_members_group_claim",
        ),
        Index("ix_claim_conflict_members_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conflict_group_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("claim_conflict_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class KnowledgeSnapshotRecord(Base):
    """Immutable published set of specifically reviewed claim values."""

    __tablename__ = "knowledge_snapshots"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_knowledge_snapshots_version"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_knowledge_snapshots_content_sha256",
        ),
        UniqueConstraint(
            "project_id",
            "version_number",
            name="uq_knowledge_snapshots_project_version",
        ),
        Index("ix_knowledge_snapshots_project_published", "project_id", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_by: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class KnowledgeSnapshotMemberRecord(Base):
    """Immutable link to the exact approving review used by a snapshot."""

    __tablename__ = "knowledge_snapshot_members"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "claim_id",
            name="uq_knowledge_snapshot_members_snapshot_claim",
        ),
        UniqueConstraint(
            "snapshot_id",
            "review_id",
            name="uq_knowledge_snapshot_members_snapshot_review",
        ),
        Index("ix_knowledge_snapshot_members_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("claim_reviews.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
