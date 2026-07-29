"""Site-adapter contracts for bounded deterministic discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from gamecrafter.domain.knowledge.sources import SourceType


@dataclass(frozen=True, slots=True)
class AdaptedSource:
    """Normalized metadata for one directly imported official page."""

    canonical_url: str
    site_key: str
    locale: str
    region: str
    source_type: SourceType
    raw_category: str | None
    classification_basis: str
    family_signal: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredPage:
    """Metadata shown for human selection before full capture."""

    canonical_url: str
    site_key: str
    locale: str
    region: str
    title: str
    source_type: SourceType
    raw_category: str | None
    classification_basis: str
    published_at: datetime | None = None
    family_signal: str | None = None


class SiteAdapter(Protocol):
    """Translate one official site's structure into shared source metadata."""

    site_key: str

    def supports(self, url: str) -> bool:
        """Return whether this adapter owns the URL."""

    def canonicalize(self, url: str) -> str:
        """Return a stable evidence identity without tracking state."""

    def adapt(self, url: str, *, title: str) -> AdaptedSource:
        """Normalize metadata for a directly imported evidence page."""

    def discover(self, html: str, *, page_url: str) -> tuple[DiscoveredPage, ...]:
        """Extract bounded candidate metadata from one listing page."""

    def browser_fallback_allowed(self, url: str) -> bool:
        """Return whether JavaScript rendering is explicitly allowed."""
