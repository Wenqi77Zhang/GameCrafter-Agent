import pytest

from gamecrafter.infrastructure.local_ai.ollama import OllamaLoopbackTransport


def test_ollama_transport_rejects_non_loopback_or_credentialed_endpoints() -> None:
    for url in (
        "https://example.com",
        "http://192.168.1.3:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434/unexpected",
    ):
        with pytest.raises(ValueError, match="local-machine"):
            OllamaLoopbackTransport(base_url=url, timeout_seconds=10)


def test_ollama_transport_accepts_local_machine_endpoints() -> None:
    OllamaLoopbackTransport(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    OllamaLoopbackTransport(base_url="http://localhost:11434", timeout_seconds=10)
    OllamaLoopbackTransport(base_url="http://host.docker.internal:11434", timeout_seconds=10)


def test_ollama_transport_probes_the_exact_model(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"models": [{"name": "qwen3.5:4b"}]}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url: str) -> FakeResponse:
            assert url == "http://127.0.0.1:11434/api/tags"
            return FakeResponse()

    monkeypatch.setattr(
        "gamecrafter.infrastructure.local_ai.ollama.httpx2.Client",
        lambda **kwargs: FakeClient(),
    )
    transport = OllamaLoopbackTransport(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    assert transport.has_model("qwen3.5:4b") is True
    assert transport.has_model("missing:latest") is False
