"""Strict loader for sanitized, source-attributed offline replay fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from gamecrafter.application.knowledge_extraction import ExtractionDocument
from gamecrafter.application.ports.model_gateway import ClaimExtractionRequest
from gamecrafter.infrastructure.models.gateways import ReplayFixture

REPLAY_FIXTURE_SCHEMA_VERSION = "gamecrafter-replay-v1"


class InvalidReplayFixtureError(ValueError):
    """Raised when an offline fixture is malformed, stale, or tampered with."""


class _SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    captured_at: datetime
    public_material_notice: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _RequestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_id: str = Field(min_length=1)
    subject_entity_key: str = Field(min_length=1)
    text: str = Field(min_length=1)
    text_start_offset: int = Field(ge=0)
    locale: str = Field(min_length=1)
    region: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _UsageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class _ReplayFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_schema_version: str
    fixture_id: str = Field(min_length=1)
    source: _SourceMetadata
    request: _RequestData
    response: dict[str, Any]
    usage: _UsageData


@dataclass(frozen=True, slots=True)
class LoadedReplayFixture:
    """Validated fixture plus its runnable document and exact gateway mapping."""

    source_url: str
    captured_at: datetime
    public_material_notice: str
    document: ExtractionDocument
    request: ClaimExtractionRequest
    fixtures: dict[str, ReplayFixture]


def load_replay_fixture(path: Path) -> LoadedReplayFixture:
    """Load one strict UTF-8 JSON fixture and verify every integrity binding."""

    try:
        raw = path.read_text(encoding="utf-8")
        parsed = _ReplayFile.model_validate_json(raw)
    except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as error:
        raise InvalidReplayFixtureError("offline replay fixture is invalid") from error

    if parsed.fixture_schema_version != REPLAY_FIXTURE_SCHEMA_VERSION:
        raise InvalidReplayFixtureError("offline replay fixture schema version is unsupported")

    request_data = parsed.request
    try:
        request = ClaimExtractionRequest(
            source_version_id=UUID(request_data.source_version_id),
            subject_entity_key=request_data.subject_entity_key,
            text=request_data.text,
            text_start_offset=request_data.text_start_offset,
            locale=request_data.locale,
            region=request_data.region,
            prompt_version=request_data.prompt_version,
            schema_version=request_data.schema_version,
        )
    except (TypeError, ValueError) as error:
        raise InvalidReplayFixtureError("offline replay request is invalid") from error

    text_digest = sha256(request.text.encode("utf-8")).hexdigest()
    if text_digest != parsed.source.text_sha256:
        raise InvalidReplayFixtureError("offline replay source text digest does not match")
    if request.fingerprint_sha256 != request_data.fingerprint_sha256:
        raise InvalidReplayFixtureError("offline replay request fingerprint does not match")
    if request.text_start_offset != 0:
        raise InvalidReplayFixtureError("document replay fixtures must begin at source offset zero")

    fixture = ReplayFixture(
        payload_json=json.dumps(
            parsed.response,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        fixture_id=parsed.fixture_id,
        input_tokens=parsed.usage.input_tokens,
        output_tokens=parsed.usage.output_tokens,
    )
    document = ExtractionDocument(
        source_version_id=request.source_version_id,
        subject_entity_key=request.subject_entity_key,
        normalized_text=request.text,
        locale=request.locale,
        region=request.region,
    )
    return LoadedReplayFixture(
        source_url=str(parsed.source.url),
        captured_at=parsed.source.captured_at,
        public_material_notice=parsed.source.public_material_notice,
        document=document,
        request=request,
        fixtures={request.fingerprint_sha256: fixture},
    )
