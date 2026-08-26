from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app


def test_health_endpoint_reports_current_foundation_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "gamecrafter-api"
    assert payload["phase"] == "M13-local"
    assert payload["version"] == "0.1.0"


def test_request_id_is_echoed_only_when_safely_bounded() -> None:
    client = TestClient(create_app())

    supplied = client.get("/health", headers={"X-Request-ID": "release-check-123"})
    replaced = client.get("/health", headers={"X-Request-ID": "unsafe request id value"})

    assert supplied.headers["X-Request-ID"] == "release-check-123"
    assert replaced.headers["X-Request-ID"] != "unsafe request id value"
    assert len(replaced.headers["X-Request-ID"]) == 32


def test_agent_catalog_discloses_all_roles_and_execution_modes() -> None:
    payload = TestClient(create_app()).get("/agents").json()

    assert payload["orchestrator"] == "durable-harness-v1"
    assert [item["key"] for item in payload["items"]] == [
        "knowledge.source_steward",
        "knowledge.curator",
        "knowledge.reviewer",
        "marketing.trend_analyst",
        "marketing.campaign_strategist",
        "creation.script_writer",
        "creation.quality_critic",
        "design.gdd_architect",
    ]
    assert [item["mode"] for item in payload["items"]].count("local_model") == 2
    assert [item["mode"] for item in payload["items"]].count("deterministic") == 6
