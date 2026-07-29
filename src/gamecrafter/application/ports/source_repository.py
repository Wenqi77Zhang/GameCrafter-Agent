"""Persistence contracts for discovery candidates and immutable source captures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gamecrafter.application.ports.object_storage import StoredObject
from gamecrafter.application.ports.site_adapter import AdaptedSource, DiscoveredPage
from gamecrafter.domain.knowledge.sources import CaptureMethod


class SourceStateError(RuntimeError):
    """Raised for missing, cross-project, or invalid source workflow state."""


@dataclass(frozen=True, slots=True)
class CaptureValidators:
    """Conditional-request validators from the latest captured version."""

    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class SelectedCandidate:
    """Human-selected discovery candidate resolved inside its owning project."""

    id: UUID
    canonical_url: str
    title: str
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """One validated official image ready to join an evidence version."""

    original_url: str
    alt_text: str | None
    stored_object: StoredObject


@dataclass(frozen=True, slots=True)
class PreparedCapture:
    """Metadata and durable object references ready for one DB transaction."""

    source: AdaptedSource
    title: str
    published_at: datetime | None
    fetched_at: datetime
    capture_method: CaptureMethod
    http_status: int
    etag: str | None
    last_modified: str | None
    raw_object: StoredObject
    normalized_object: StoredObject
    images: tuple[PreparedImage, ...]
    image_candidate_count: int
    image_failure_count: int
    evidence_fingerprint_sha256: str
    parser_version: str
    capture_policy_version: str
    document_language: str | None


@dataclass(frozen=True, slots=True)
class PersistedCapture:
    """Identity and version outcome returned by an idempotent capture write."""

    source_id: UUID
    source_version_id: UUID
    version_number: int
    created_version: bool


class SourceRepository(Protocol):
    """Transactional source persistence independent from SQLAlchemy."""

    def save_candidates(
        self,
        *,
        run_id: UUID,
        candidates: tuple[DiscoveredPage, ...],
    ) -> int:
        """Insert new candidates for a run and return the number added."""

    def capture_validators(self, *, run_id: UUID, canonical_url: str) -> CaptureValidators | None:
        """Return latest HTTP validators for this run's project and URL."""

    def selected_candidate(self, *, run_id: UUID, candidate_id: UUID) -> SelectedCandidate:
        """Resolve a selected candidate in the capture run's project."""

    def record_not_modified(
        self,
        *,
        run_id: UUID,
        canonical_url: str,
        candidate_id: UUID | None,
    ) -> PersistedCapture:
        """Record a 304 result and link an optional selected candidate."""

    def persist_capture(
        self,
        *,
        run_id: UUID,
        candidate_id: UUID | None,
        capture: PreparedCapture,
    ) -> PersistedCapture:
        """Create or reuse an immutable source version transactionally."""
