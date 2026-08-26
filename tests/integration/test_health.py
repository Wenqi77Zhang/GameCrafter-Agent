from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app


def test_health_endpoint_reports_current_foundation_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "gamecrafter-api"
    assert payload["phase"] == "M12-local"
    assert payload["version"] == "0.1.0"


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
