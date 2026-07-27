"""SQLAlchemy records for the M1-A durable foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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
