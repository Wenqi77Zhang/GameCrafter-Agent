from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app


def test_health_endpoint_reports_current_foundation_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "gamecrafter-api"
    assert payload["phase"] == "M1-B"
    assert payload["version"] == "0.1.0"
