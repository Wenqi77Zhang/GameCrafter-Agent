"""Loopback-only Ollama HTTP transport kept outside the model gateway boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx2


class OllamaLoopbackTransport:
    """Post structured chat requests only to a local Ollama endpoint."""

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama must use a local loopback HTTP endpoint")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._timeout_seconds = timeout_seconds

    def __call__(self, payload: dict[str, Any]) -> Mapping[str, Any]:
        with httpx2.Client(trust_env=False, timeout=self._timeout_seconds) as client:
            response = client.post(self._url, json=payload)
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, Mapping):
            raise ValueError("Ollama returned a non-object response")
        return result
