"""Coverage-bound review contracts; factual entailment is still a model judgment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field

from gamecrafter.application.creative import CreativeError, StrictOutput

MAX_REVIEW_TEXTS = 96
REVIEW_BATCH_SIZE = 8


class EvidenceDecision(StrictOutput):
    reason: str = Field(min_length=1, max_length=400)
    evidence_keys: list[str] = Field(max_length=8)
    evidence_quotes: list[str] = Field(max_length=8)
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "NOT_A_FACT"]


class EvidenceBatch(StrictOutput):
    assessments: dict[str, EvidenceDecision]


@dataclass(frozen=True)
class ReviewText:
    text_id: str
    field: str
    section_index: int | None
    text: str


def _fragments(text: str):
    """Preserve every non-whitespace character, with bounded exact draft substrings."""
    remaining = text.strip()
    while remaining:
        if len(remaining) <= 600:
            yield remaining
            return
        # Prefer a sentence/word boundary, but never silently truncate a long token.
        boundaries = [m.end() for m in re.finditer(r"[.!?。！？]\s+|\s+", remaining[:600])]
        end = boundaries[-1] if boundaries and boundaries[-1] >= 200 else 600
        yield remaining[:end].rstrip()
        remaining = remaining[end:].lstrip()


def review_texts(draft: dict[str, Any]) -> list[ReviewText]:
    """Enumerate actual authored fields, excluding IDs, timings and execution metadata."""
    if not isinstance(draft, dict):
        raise CreativeError("待核查文案必须是结构化对象。")
    fields: list[tuple[str, int | None, str]] = []

    def add(field: str, value: Any, index=None):
        if isinstance(value, str) and value.strip():
            fields.append((field, index, value))
        elif isinstance(value, list):
            for ordinal, item in enumerate(value):
                add(f"{field}.{ordinal}", item, index)

    for key in (
        "title",
        "caption",
        "hashtags",
        "voiceover",
        "on_screen_text",
        "visual_direction",
        "marketing_direction",
        "recommended_topic",
        "why_it_fits",
        "target_audience",
        "english_hooks",
        "execution_steps",
        "measurement_plan",
        "risks",
    ):
        add(key, draft.get(key))
    sections = draft.get("sections", [])
    if not isinstance(sections, list):
        raise CreativeError("待核查分镜必须是列表。")
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or index > 11:
            raise CreativeError("待核查分镜格式无效，或超过 12 镜的上限。")
        for key in ("voiceover", "on_screen_text", "visual_direction"):
            add(f"sections.{index}.{key}", section.get(key), index)
    texts = [
        ReviewText(f"t{ordinal}", field, index, fragment)
        for ordinal, (field, index, fragment) in enumerate(
            (field, index, fragment)
            for field, index, text in fields
            for fragment in _fragments(text)
        )
    ]
    if not texts or len(texts) > MAX_REVIEW_TEXTS:
        raise CreativeError("没有可核查的文案，或文案超过 96 段的核查上限。请缩小内容后重试。")
    return texts


def validate_evidence_batch(result: EvidenceBatch, context: dict) -> None:
    if set(result.assessments) != {item["text_id"] for item in context["texts"]}:
        raise CreativeError("核查没有完整覆盖指定文案，或增加了不存在的文案编号。")
    allowed = set(context["evidence"])
    for decision in result.assessments.values():
        if len(set(decision.evidence_keys)) != len(decision.evidence_keys):
            raise CreativeError("核查重复引用了同一证据。")
        if not set(decision.evidence_keys).issubset(allowed):
            raise CreativeError("核查引用了未提供的证据。")
        if len(decision.evidence_keys) != len(decision.evidence_quotes):
            raise CreativeError("每项证据引用必须对应一段原文。")
        for key, quote in zip(decision.evidence_keys, decision.evidence_quotes, strict=True):
            evidence = context["evidence"][key]
            if not quote.strip() or not any(quote in text for text in _strings(evidence["value"])):
                raise CreativeError("核查引文不在所引用的已审核事实中。")
        if decision.verdict == "SUPPORTED" and not decision.evidence_keys:
            raise CreativeError("声称有事实支持的文案必须列出所提供的证据。")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif value is not None:
        yield str(value)
