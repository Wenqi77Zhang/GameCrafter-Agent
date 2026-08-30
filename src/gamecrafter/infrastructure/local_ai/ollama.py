"""Loopback-only Ollama HTTP transport kept outside the model gateway boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx2


class OllamaLoopbackTransport:
    """Talk only to Ollama on this machine, including Docker's exact host alias."""

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama must use an approved local-machine HTTP endpoint")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._base_url = base_url.rstrip("/")
        self._url = f"{self._base_url}/api/chat"
        self._timeout_seconds = timeout_seconds

    def has_model(self, model: str) -> bool:
        """Return whether Ollama currently exposes the exact configured local model."""

        if not model.strip():
            return False
        with httpx2.Client(trust_env=False, timeout=min(self._timeout_seconds, 3.0)) as client:
            response = client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, Mapping):
            return False
        models = result.get("models")
        if not isinstance(models, list):
            return False
        return any(
            isinstance(item, Mapping) and (item.get("name") == model or item.get("model") == model)
            for item in models
        )

    def __call__(self, payload: dict[str, Any]) -> Mapping[str, Any]:
        with httpx2.Client(trust_env=False, timeout=self._timeout_seconds) as client:
            response = client.post(self._url, json=payload)
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, Mapping):
            raise ValueError("Ollama returned a non-object response")
        return result
