import json
import socket
from pathlib import Path

import pytest

from gamecrafter.application.knowledge_extraction import ExtractionHarness
from gamecrafter.application.text_chunking import DeterministicTextChunker
from gamecrafter.infrastructure.models.gateways import ReplayModelGateway
from gamecrafter.infrastructure.models.replay_fixtures import (
    InvalidReplayFixtureError,
    load_replay_fixture,
)

NTE_FIXTURE = Path("fixtures/nte/official-homepage-en-v1.json")


def test_official_nte_fixture_runs_as_exact_zero_cost_offline_replay(monkeypatch) -> None:
    def deny_network(*args, **kwargs):
        del args, kwargs
        raise AssertionError("offline replay attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    loaded = load_replay_fixture(NTE_FIXTURE)
    harness = ExtractionHarness(
        gateway=ReplayModelGateway(loaded.fixtures),
        chunker=DeterministicTextChunker(),
    )

    result = harness.run(loaded.document)

    assert loaded.source_url == "https://nte.perfectworld.com/en/main.html"
    assert "not an internal GDD" in loaded.public_material_notice
    assert result.usage.total_tokens == 0
    assert [claim.predicate.value for claim in result.claims] == [
        "genre.primary",
        "game.developer",
    ]
    assert result.claims[1].evidence[0].quote == "Hotta Studio"
    assert result.invocations[0].response_id == "nte-official-homepage-en-20260801-v1"


def test_fixture_loader_rejects_tampered_source_text(tmp_path: Path) -> None:
    payload = json.loads(NTE_FIXTURE.read_text(encoding="utf-8"))
    payload["request"]["text"] += " tampered"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidReplayFixtureError, match="digest does not match"):
        load_replay_fixture(tampered)


def test_fixture_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    payload = json.loads(NTE_FIXTURE.read_text(encoding="utf-8"))
    payload["source"]["private_path"] = "C:/secret/source.html"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidReplayFixtureError, match="fixture is invalid"):
        load_replay_fixture(invalid)
