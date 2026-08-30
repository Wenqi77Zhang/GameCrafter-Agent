"""Versioned specialist catalog for the constrained GameCrafter runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentMode(StrEnum):
    LOCAL_MODEL = "local_model"
    DETERMINISTIC = "deterministic"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    key: str
    name: str
    version: str
    mode: AgentMode
    reasoning_pattern: str
    human_gate_after: bool


SOURCE_STEWARD = AgentSpec(
    "knowledge.source_steward",
    "Source and Provenance Steward",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "bounded source validation and provenance capture",
    True,
)


KNOWLEDGE_CURATOR = AgentSpec(
    "knowledge.curator",
    "Knowledge Curator",
    "2.0.0",
    AgentMode.LOCAL_MODEL,
    "bounded structured extraction",
    False,
)
KNOWLEDGE_REVIEWER = AgentSpec(
    "knowledge.reviewer",
    "Knowledge Reviewer",
    "1.2.0",
    AgentMode.LOCAL_MODEL,
    "independent adversarial review",
    True,
)
TREND_ANALYST = AgentSpec(
    "marketing.trend_analyst",
    "Trend Analyst",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "bounded evidence analysis",
    False,
)
CAMPAIGN_STRATEGIST = AgentSpec(
    "marketing.campaign_strategist",
    "Campaign Strategist",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "plan from frozen evidence",
    True,
)
SCRIPT_WRITER = AgentSpec(
    "creation.script_writer",
    "Script Writer",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "structured generation",
    False,
)
QUALITY_CRITIC = AgentSpec(
    "creation.quality_critic",
    "Quality and Compliance Critic",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "bounded evaluator optimizer",
    True,
)
GDD_ARCHITECT = AgentSpec(
    "design.gdd_architect",
    "GDD Architect",
    "1.0.0",
    AgentMode.DETERMINISTIC,
    "exact-offset chapter structuring and assumption separation",
    True,
)

AGENT_CATALOG = (
    SOURCE_STEWARD,
    KNOWLEDGE_CURATOR,
    KNOWLEDGE_REVIEWER,
    TREND_ANALYST,
    CAMPAIGN_STRATEGIST,
    SCRIPT_WRITER,
    QUALITY_CRITIC,
    GDD_ARCHITECT,
)


def public_agent_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": item.key,
            "name": item.name,
            "version": item.version,
            "mode": item.mode.value,
            "reasoning_pattern": item.reasoning_pattern,
            "human_gate_after": item.human_gate_after,
        }
        for item in AGENT_CATALOG
    ]
