from io import BytesIO

import pytest

from gamecrafter.application.ports.object_storage import (
    InvalidObjectKeyError,
    ObjectIntegrityError,
    ObjectTooLargeError,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def test_local_storage_is_content_addressed_and_deduplicated(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")

    first = storage.put(BytesIO(b"same evidence"), media_type="text/html")
    second = storage.put(BytesIO(b"same evidence"), media_type="text/html")

    assert first.key == second.key
    assert first.digest == second.digest
    assert first.size_bytes == len(b"same evidence")
    assert storage.exists(first.key)
    with storage.open(first.key) as stored:
        assert stored.read() == b"same evidence"
    assert len(list((tmp_path / "objects" / "sha256").rglob(first.digest.value))) == 1


def test_local_storage_rejects_oversized_stream_without_publishing(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")

    with pytest.raises(ObjectTooLargeError, match="4-byte"):
        storage.put(BytesIO(b"12345"), media_type="text/plain", max_bytes=4)

    assert list((tmp_path / "objects" / "sha256").glob("**/*")) == []
    assert list((tmp_path / "objects" / ".tmp").iterdir()) == []


def test_local_storage_rejects_path_traversal_keys(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")

    with pytest.raises(InvalidObjectKeyError):
        storage.open("../../outside")


def test_local_storage_detects_corrupt_existing_object(tmp_path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")
    stored = storage.put(BytesIO(b"trusted"), media_type="text/plain")
    object_path = tmp_path / "objects" / stored.key
    object_path.write_bytes(b"corrupt")

    with pytest.raises(ObjectIntegrityError, match="does not match"):
        storage.put(BytesIO(b"trusted"), media_type="text/plain")
