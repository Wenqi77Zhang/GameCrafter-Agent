import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from gamecrafter.application.ports.model_gateway import (
    ClaimExtractionRequest,
    InvalidModelOutputError,
    ModelGatewayDisabledError,
    ModelProviderError,
    ReplayFixtureNotFoundError,
)
from gamecrafter.infrastructure.models.gateways import (
    CLAIM_PROMPT_VERSION,
    CLAIM_SCHEMA_VERSION,
    DisabledModelGateway,
    OpenAIResponsesGateway,
    ReplayFixture,
    ReplayModelGateway,
)
from gamecrafter.infrastructure.models.structured_claims import strict_claim_schema


def extraction_request(*, text_start_offset: int = 100) -> ClaimExtractionRequest:
    return ClaimExtractionRequest(
        source_version_id=UUID("00000000-0000-0000-0000-000000000123"),
        subject_entity_key="game:nte",
        text="Neverness to Everness is an urban open-world RPG.",
        text_start_offset=text_start_offset,
        locale="en",
        region="global",
        prompt_version=CLAIM_PROMPT_VERSION,
        schema_version=CLAIM_SCHEMA_VERSION,
    )


def valid_payload() -> dict[str, object]:
    return {
        "claims": [
            {
                "predicate": "game.name",
                "value_kind": "string",
                "value": "Neverness to Everness",
                "confidence": 0.95,
                "evidence": [
                    {
                        "start_offset": 0,
                        "end_offset": 21,
                        "quote": "Neverness to Everness",
                    }
                ],
            }
        ]
    }


def test_request_fingerprint_binds_prompt_schema_and_exact_text() -> None:
    request = extraction_request()
    changed = ClaimExtractionRequest(
        source_version_id=request.source_version_id,
        subject_entity_key=request.subject_entity_key,
        text=f"{request.text} ",
        text_start_offset=request.text_start_offset,
        locale=request.locale,
        region=request.region,
        prompt_version=request.prompt_version,
        schema_version=request.schema_version,
    )

    assert len(request.fingerprint_sha256) == 64
    assert request.fingerprint_sha256 != changed.fingerprint_sha256


def test_disabled_gateway_fails_closed() -> None:
    with pytest.raises(ModelGatewayDisabledError, match="disabled"):
        DisabledModelGateway().extract_claims(extraction_request())


def test_replay_gateway_requires_an_exact_fixture_and_absolutizes_evidence() -> None:
    request = extraction_request()
    gateway = ReplayModelGateway(
        {
            request.fingerprint_sha256: ReplayFixture(
                payload_json=json.dumps(valid_payload()),
                fixture_id="nte-minimal-v1",
                input_tokens=20,
                output_tokens=30,
            )
        }
    )

    result = gateway.extract_claims(request)

    assert result.provider == "replay"
    assert result.response_id == "nte-minimal-v1"
    assert result.usage.total_tokens == 50
    assert result.claims[0].evidence[0].start_offset == 100
    assert result.claims[0].evidence[0].end_offset == 121


def test_replay_gateway_rejects_missing_or_inexact_evidence() -> None:
    request = extraction_request()
    with pytest.raises(ReplayFixtureNotFoundError, match="exact request"):
        ReplayModelGateway({}).extract_claims(request)

    payload = valid_payload()
    payload["claims"][0]["evidence"][0]["quote"] = "Invented title"
    gateway = ReplayModelGateway(
        {
            request.fingerprint_sha256: ReplayFixture(
                payload_json=json.dumps(payload),
                fixture_id="invalid",
            )
        }
    )
    with pytest.raises(InvalidModelOutputError, match="does not match"):
        gateway.extract_claims(request)


def test_strict_schema_forbids_undeclared_object_properties() -> None:
    schema = strict_claim_schema()

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["StructuredCandidateClaim"]["additionalProperties"] is False
    assert schema["$defs"]["StructuredEvidenceSpan"]["additionalProperties"] is False
    confidence = schema["$defs"]["StructuredCandidateClaim"]["properties"]["confidence"]
    assert confidence["minimum"] == 0
    assert confidence["maximum"] == 1
    assert {"ge", "le"}.isdisjoint(nested_keys(schema))


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value))
    return set()


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def fake_client(responses: FakeResponses) -> object:
    return SimpleNamespace(responses=responses)


def test_openai_adapter_uses_store_false_and_strict_structured_output() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            id="resp_fixture_123",
            status="completed",
            output_text=json.dumps(valid_payload()),
            usage=SimpleNamespace(input_tokens=50, output_tokens=25, total_tokens=75),
        )
    )
    gateway = OpenAIResponsesGateway(fake_client(responses))

    result = gateway.extract_claims(extraction_request())

    assert result.provider == "openai"
    assert result.model == "gpt-5.6-terra"
    assert result.usage.total_tokens == 75
    assert responses.kwargs is not None
    assert responses.kwargs["store"] is False
    assert responses.kwargs["reasoning"] == {"effort": "low"}
    text = responses.kwargs["text"]
    assert text["format"]["type"] == "json_schema"
    assert text["format"]["strict"] is True
    assert "source_version_id" not in json.dumps(responses.kwargs["input"])


def test_openai_adapter_rejects_incomplete_or_malformed_output() -> None:
    incomplete = FakeResponses(
        SimpleNamespace(
            id="resp_incomplete",
            status="incomplete",
            output_text=json.dumps(valid_payload()),
            usage=None,
        )
    )
    with pytest.raises(ModelProviderError, match="did not complete"):
        OpenAIResponsesGateway(fake_client(incomplete)).extract_claims(extraction_request())

    malformed = FakeResponses(
        SimpleNamespace(
            id="resp_malformed",
            status="completed",
            output_text='{"claims":[{"unexpected":true}]}',
            usage=None,
        )
    )
    with pytest.raises(InvalidModelOutputError, match="strict claim schema"):
        OpenAIResponsesGateway(fake_client(malformed)).extract_claims(extraction_request())


def test_openai_adapter_redacts_provider_exception_text() -> None:
    responses = FakeResponses(error=RuntimeError("secret-key-and-prompt-must-not-leak"))

    with pytest.raises(ModelProviderError) as raised:
        OpenAIResponsesGateway(fake_client(responses)).extract_claims(extraction_request())

    assert "secret-key" not in str(raised.value)
    assert "RuntimeError" in str(raised.value)
