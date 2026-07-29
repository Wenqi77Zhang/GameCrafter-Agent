"""Outbound contracts for deterministic official-source capture."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from gamecrafter.domain.knowledge.sources import CaptureMethod

GAMECRAFTER_USER_AGENT = "GameCrafter"


class SourceAccessError(RuntimeError):
    """Base error for policy or capture failures safe to classify upstream."""


class CaptureError(SourceAccessError):
    """Base error for a bounded capture that could not produce evidence."""


class RedirectLimitError(CaptureError):
    """Raised before following more redirects than the request allows."""


class ResponseTooLargeError(CaptureError):
    """Raised when headers or streamed bytes exceed the request budget."""


class UnsupportedMediaTypeError(CaptureError):
    """Raised when a response is not one of the expected evidence types."""


class UpstreamStatusError(CaptureError):
    """Raised for a terminal non-success response from an official source."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"official source returned HTTP {status_code}")


class BrowserUnavailableError(CaptureError):
    """Raised when Playwright or its Chromium runtime is unavailable."""


class RobotsDeniedError(SourceAccessError):
    """Raised when an official origin's robots rules deny a requested page."""


class CapturePurpose(StrEnum):
    """Application-level reason for one controlled HTTP request."""

    PAGE = "page"
    ROBOTS = "robots"
    ASSET = "asset"


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    """One policy-approved page request with explicit resource budgets."""

    url: str
    max_bytes: int
    timeout_seconds: float
    max_redirects: int
    accepted_media_types: tuple[str, ...] = ("text/html",)
    ready_selector: str | None = None
    request_headers: Mapping[str, str] | None = None
    max_subresources: int = 100
    purpose: CapturePurpose = CapturePurpose.PAGE

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        if not self.accepted_media_types:
            raise ValueError("accepted_media_types cannot be empty")
        if self.max_subresources < 0:
            raise ValueError("max_subresources cannot be negative")


@dataclass(frozen=True, slots=True)
class CapturedPage:
    """Bounded response bytes and replay-relevant capture metadata."""

    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    method: CaptureMethod


@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    """Deterministic visible text and metadata derived from captured HTML."""

    title: str
    normalized_text: str
    document_language: str | None
    metadata: Mapping[str, str]
    images: tuple[EvidenceImage, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceImage:
    """One bounded image candidate referenced by the captured document."""

    url: str
    alt_text: str | None


class PageFetcher(Protocol):
    """Capture adapter implemented by HTTP and controlled browsers."""

    def fetch(self, request: CaptureRequest) -> CapturedPage:
        """Capture one page or raise a typed, user-visible failure."""


class RequestScheduler(Protocol):
    """Coordinate bounded outbound access inside one worker process."""

    def slot(self, url: str) -> AbstractContextManager[None]:
        """Reserve one host/global request slot and apply minimum spacing."""

    def update_host_interval(self, hostname: str, seconds: float) -> None:
        """Raise one host's minimum interval when robots.txt requires it."""


class RobotsPolicy(Protocol):
    """Authorize a page against cached official robots rules."""

    def ensure_allowed(self, url: str) -> object:
        """Raise a typed error when the page is disallowed."""
