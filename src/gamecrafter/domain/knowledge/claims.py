"""Framework-independent vocabulary for reviewable game knowledge claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any


class EntityType(StrEnum):
    """Controlled subject types for the first Knowledge Hub slice."""

    GAME = "game"
    CHARACTER = "character"
    ORGANIZATION = "organization"
    LOCATION = "location"
    FACTION = "faction"
    PLATFORM = "platform"
    GAMEPLAY_SYSTEM = "gameplay_system"
    EVENT = "event"
    OTHER = "other"


class FactPredicate(StrEnum):
    """Controlled fact types that a model may emit in M1-C."""

    GAME_NAME = "game.name"
    GAME_ALIAS = "game.alias"
    GAME_DEVELOPER = "game.developer"
    GAME_PUBLISHER = "game.publisher"
    RELEASE_STATUS = "release.status"
    RELEASE_DATE = "release.date"
    PLATFORM_AVAILABILITY = "platform.availability"
    BUSINESS_MODEL = "business.model"
    GENRE_PRIMARY = "genre.primary"
    WORLD_SETTING = "world.setting"
    WORLD_LOCATION = "world.location"
    FACTION_DESCRIPTION = "faction.description"
    CHARACTER_IDENTITY = "character.identity"
    CHARACTER_AFFILIATION = "character.affiliation"
    CHARACTER_ABILITY = "character.ability"
    GAMEPLAY_COMBAT = "gameplay.combat"
    GAMEPLAY_EXPLORATION = "gameplay.exploration"
    GAMEPLAY_VEHICLE = "gameplay.vehicle"
    GAMEPLAY_QUEST = "gameplay.quest"
    GAMEPLAY_MULTIPLAYER = "gameplay.multiplayer"
    FEATURE_DESCRIPTION = "feature.description"
    EVENT_SCHEDULE = "event.schedule"
    UPDATE_CHANGE = "update.change"
    UNCLASSIFIED = "unclassified"


class ClaimValueKind(StrEnum):
    """JSON value shape used for validation and deterministic comparison."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENTITY_REF = "entity_ref"
    STRING_LIST = "string_list"


class ReviewDecision(StrEnum):
    """Append-only human decision over one immutable model claim."""

    APPROVE = "approve"
    APPROVE_WITH_EDIT = "approve_with_edit"
    REJECT = "reject"
    DEFER = "defer"


class ConflictRelation(StrEnum):
    """Deterministic relationship between claims sharing a comparison key."""

    CONFLICTING = "conflicting"
    POSSIBLY_COEXISTING = "possibly_coexisting"


class ConflictStatus(StrEnum):
    """Human-controlled lifecycle of one potential conflict group."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """Exact visible-text range supporting a candidate claim."""

    start_offset: int
    end_offset: int
    quote: str

    def __post_init__(self) -> None:
        if self.start_offset < 0:
            raise ValueError("evidence start_offset must be nonnegative")
        if self.end_offset <= self.start_offset:
            raise ValueError("evidence end_offset must be after start_offset")
        if not self.quote.strip():
            raise ValueError("evidence quote must not be blank")
        if self.end_offset - self.start_offset != len(self.quote):
            raise ValueError("evidence range length must equal quote length")

    @property
    def quote_sha256(self) -> str:
        """Return the stable digest retained beside the reviewable quote."""

        return sha256(self.quote.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    """Validated model output before persistence or human review."""

    predicate: FactPredicate
    value_kind: ClaimValueKind
    value: Any
    confidence: float
    evidence: tuple[EvidenceSpan, ...]

    def __post_init__(self) -> None:
        if isinstance(self.confidence, bool) or not 0 <= self.confidence <= 1:
            raise ValueError("claim confidence must be between 0 and 1")
        if not self.evidence:
            raise ValueError("candidate claim must contain at least one evidence span")
        _validate_value(self.value_kind, self.value)


def _validate_value(kind: ClaimValueKind, value: Any) -> None:
    if kind in {ClaimValueKind.STRING, ClaimValueKind.DATE, ClaimValueKind.DATETIME}:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{kind.value} claim value must be a non-empty string")
        return
    if kind is ClaimValueKind.NUMBER:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("number claim value must be numeric")
        return
    if kind is ClaimValueKind.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError("boolean claim value must be true or false")
        return
    if kind is ClaimValueKind.ENTITY_REF:
        if not isinstance(value, dict) or set(value) != {"entity_key"}:
            raise ValueError("entity_ref value must contain only entity_key")
        if not isinstance(value["entity_key"], str) or not value["entity_key"].strip():
            raise ValueError("entity_ref entity_key must be a non-empty string")
        return
    if kind is ClaimValueKind.STRING_LIST:
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise ValueError("string_list claim value must contain non-empty strings")
        return
    raise ValueError(f"unsupported claim value kind: {kind}")
