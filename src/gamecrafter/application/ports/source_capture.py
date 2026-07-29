"""Outbound contracts for deterministic official-source capture."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from gamecrafter.domain.knowledge.sources import CaptureMethod


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


class PageFetcher(Protocol):
    """Capture adapter implemented by HTTP and controlled browsers."""

    def fetch(self, request: CaptureRequest) -> CapturedPage:
        """Capture one page or raise a typed, user-visible failure."""
