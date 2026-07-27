from gamecrafter.api.app import create_app


def test_health_contract_is_published_in_openapi() -> None:
    schema = create_app().openapi()

    assert "/health" in schema["paths"]
    response_schema = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert "content" in response_schema
