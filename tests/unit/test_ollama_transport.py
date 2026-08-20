import pytest

from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport


def test_ollama_transport_rejects_non_loopback_or_credentialed_endpoints() -> None:
    for url in (
        "https://example.com",
        "http://192.168.1.3:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434/unexpected",
    ):
        with pytest.raises(ValueError, match="loopback"):
            OllamaLoopbackTransport(base_url=url, timeout_seconds=10)


def test_ollama_transport_accepts_localhost_only() -> None:
    OllamaLoopbackTransport(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    OllamaLoopbackTransport(base_url="http://localhost:11434", timeout_seconds=10)
