"""Large-object persistence boundary for source evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from gamecrafter.domain.knowledge.sources import EvidenceDigest


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Metadata returned after durable content-addressed storage."""

    key: str
    digest: EvidenceDigest
    size_bytes: int
    media_type: str


class ObjectTooLargeError(ValueError):
    """Raised before an object can exceed its configured byte budget."""


class InvalidObjectKeyError(ValueError):
    """Raised when an object key is not a canonical content-addressed key."""


class ObjectIntegrityError(OSError):
    """Raised when existing bytes do not match their content-addressed key."""


class ObjectStorage(Protocol):
    """Storage contract independent from filesystem and cloud vendors."""

    def put(
        self,
        source: BinaryIO,
        *,
        media_type: str,
        max_bytes: int | None = None,
    ) -> StoredObject:
        """Persist a stream once and return immutable metadata."""

    def open(self, key: str) -> BinaryIO:
        """Open a stored object for binary reading."""

    def exists(self, key: str) -> bool:
        """Return whether a validated key exists."""

    def delete(self, key: str) -> None:
        """Permanently remove one validated object."""
