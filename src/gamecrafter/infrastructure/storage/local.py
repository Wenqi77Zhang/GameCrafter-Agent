"""Private local content-addressed object storage."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from gamecrafter.application.ports.object_storage import (
    InvalidObjectKeyError,
    ObjectIntegrityError,
    ObjectTooLargeError,
    StoredObject,
)
from gamecrafter.domain.knowledge.sources import EvidenceDigest

_BUFFER_SIZE = 1024 * 1024
_KEY_PATTERN = re.compile(r"^sha256/[0-9a-f]{2}/[0-9a-f]{64}$")


class LocalObjectStorage:
    """Store immutable objects below one configured private directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._temporary = self._root / ".tmp"
        self._temporary.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        source: BinaryIO,
        *,
        media_type: str,
        max_bytes: int | None = None,
    ) -> StoredObject:
        """Stream to a temporary file, validate size, then atomically publish."""

        digest = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(dir=self._temporary, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := source.read(_BUFFER_SIZE):
                    size_bytes += len(chunk)
                    if max_bytes is not None and size_bytes > max_bytes:
                        raise ObjectTooLargeError(
                            f"object exceeded the {max_bytes}-byte storage limit"
                        )
                    digest.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

            evidence_digest = EvidenceDigest(digest.hexdigest())
            key = self._key_for(evidence_digest)
            destination = self._path_for(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                self._verify_existing(destination, evidence_digest, size_bytes)
                temporary_path.unlink()
            else:
                os.replace(temporary_path, destination)
            temporary_path = None
            return StoredObject(
                key=key,
                digest=evidence_digest,
                size_bytes=size_bytes,
                media_type=media_type,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def open(self, key: str) -> BinaryIO:
        """Open a validated object without allowing path traversal."""

        return self._path_for(key).open("rb")

    def exists(self, key: str) -> bool:
        """Check a validated content-addressed key."""

        return self._path_for(key).is_file()

    def delete(self, key: str) -> None:
        """Remove one object after application-level reference checks."""

        self._path_for(key).unlink(missing_ok=True)

    @staticmethod
    def _key_for(digest: EvidenceDigest) -> str:
        return f"sha256/{digest.value[:2]}/{digest.value}"

    def _path_for(self, key: str) -> Path:
        if _KEY_PATTERN.fullmatch(key) is None:
            raise InvalidObjectKeyError("object key is not a canonical SHA-256 key")
        candidate = (self._root / Path(*key.split("/"))).resolve()
        if not candidate.is_relative_to(self._root):
            raise InvalidObjectKeyError("object key escaped the storage root")
        return candidate

    @staticmethod
    def _verify_existing(
        path: Path,
        expected_digest: EvidenceDigest,
        expected_size: int,
    ) -> None:
        if path.stat().st_size != expected_size:
            raise ObjectIntegrityError("existing object size does not match its key")
        digest = hashlib.sha256()
        with path.open("rb") as stored:
            while chunk := stored.read(_BUFFER_SIZE):
                digest.update(chunk)
        if digest.hexdigest() != expected_digest.value:
            raise ObjectIntegrityError("existing object content does not match its key")
