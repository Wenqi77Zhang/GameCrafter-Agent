from gamecrafter.api.app import create_app


def test_health_contract_is_published_in_openapi() -> None:
    schema = create_app().openapi()

    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]
    assert "/api/projects" in schema["paths"]
    assert "/api/projects/{project_id}/source-discoveries" in schema["paths"]
    assert "/api/projects/{project_id}/source-imports" in schema["paths"]
    assert "/api/projects/{project_id}/sources" in schema["paths"]
    assert "/api/projects/{project_id}/candidates" in schema["paths"]
    assert "/api/projects/{project_id}/runs" in schema["paths"]
    assert "/api/runs/{run_id}/events" in schema["paths"]
    response_schema = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert "content" in response_schema
