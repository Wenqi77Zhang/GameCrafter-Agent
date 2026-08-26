"""Framework-independent source evidence vocabulary and invariants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from string import hexdigits


class SourceType(StrEnum):
    """Normalized page types shared across site-specific categories."""

    OVERVIEW = "overview"
    CHARACTER = "character"
    WORLD = "world"
    GAMEPLAY = "gameplay"
    NEWS = "news"
    UPDATE = "update"
    EVENT = "event"
    GUIDE_FAQ = "guide_faq"
    DOCUMENT = "document"
    TRANSCRIPT = "transcript"
    GDD = "gdd"
    OTHER = "other"


class SourceStatus(StrEnum):
    """User-controlled lifecycle of one canonical source."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class CandidateStatus(StrEnum):
    """Lifecycle of a page discovered before capture."""

    DISCOVERED = "discovered"
    SELECTED = "selected"
    IMPORTED = "imported"
    SKIPPED = "skipped"


class CaptureMethod(StrEnum):
    """Deterministic mechanism that produced a source snapshot."""

    HTTP = "http"
    PLAYWRIGHT = "playwright"
    LOCAL_UPLOAD = "local_upload"


class ChangeKind(StrEnum):
    """Meaningful evidence relationship to the preceding version."""

    INITIAL = "initial"
    MEANINGFUL = "meaningful"


class AssetRole(StrEnum):
    """Purpose of a stored object inside an immutable source version."""

    RAW_HTML = "raw_html"
    RAW_DOCUMENT = "raw_document"
    NORMALIZED_TEXT = "normalized_text"
    IMAGE = "image"


@dataclass(frozen=True, slots=True)
class EvidenceDigest:
    """Validated SHA-256 digest used by domain and storage boundaries."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower()
        if len(normalized) != 64 or any(character not in hexdigits for character in normalized):
            raise ValueError("evidence digest must be a 64-character SHA-256 hex value")
        object.__setattr__(self, "value", normalized)
