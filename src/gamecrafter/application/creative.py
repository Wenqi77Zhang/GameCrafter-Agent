"""Bounded creative contracts: models propose; deterministic gates retain authority."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

PROMPT_VERSION = "creative-evidence-v7"
RULE_VERSION = "script-readiness-v3"
PURPOSES = ("hook", "setup", "proof", "payoff", "cta")
CHINESE_TEXT = r"^[\s\S]*[\u4e00-\u9fff][\s\S]*$"


class CreativeError(RuntimeError):
    """Safe, user-visible model or contract failure; never a silent template fallback."""


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Beat(StrictOutput):
    voiceover: str = Field(min_length=1, max_length=1200)
    on_screen_text: str = Field(min_length=1, max_length=300)
    visual_direction: str = Field(min_length=1, max_length=1000)
    knowledge_member_ids: list[str] = Field(max_length=8)


class ScriptDraft(StrictOutput):
    title: str = Field(min_length=1, max_length=200)
    caption: str = Field(min_length=1, max_length=500)
    hashtags: list[str] = Field(min_length=1, max_length=6)
    beats: list[Beat] = Field(min_length=5, max_length=5)


class Strategy(StrictOutput):
    marketing_direction: str = Field(
        min_length=5, max_length=600, pattern=CHINESE_TEXT, description="用简体中文写营销角度"
    )
    recommended_topic: str = Field(
        min_length=5,
        max_length=400,
        pattern=CHINESE_TEXT,
        description="中文完整句子：这条视频具体讲什么；不是标签列表",
    )
    why_it_fits: str = Field(
        min_length=10,
        max_length=1000,
        pattern=CHINESE_TEXT,
        description="用简体中文解释事实关联，不引用规则分数",
    )
    target_audience: str = Field(
        min_length=3, max_length=400, pattern=CHINESE_TEXT, description="用简体中文说明目标受众"
    )
    english_hooks: list[str] = Field(min_length=2, max_length=3)
    execution_steps: list[str] = Field(min_length=3, max_length=5)
    risks: list[str] = Field(min_length=1, max_length=6)
    knowledge_member_ids: list[str] = Field(min_length=1, max_length=8)
    measurement_plan: str = Field(
        min_length=5,
        max_length=600,
        pattern=CHINESE_TEXT,
        description="简体中文。说明A/B比较方式，不设数字达标阈值",
    )


class CriticIssue(StrictOutput):
    draft_quote: str = Field(
        min_length=1,
        max_length=600,
        description="Exact text copied from draft, not from instructions or facts",
    )
    section_index: StrictInt | None = Field(ge=0, le=11)
    severity: Literal["blocking", "warning"]
    category: Literal["evidence", "pacing", "clarity", "safety", "brief_fit"]
    message: str = Field(min_length=3, max_length=600)
    fix: str = Field(min_length=3, max_length=600)


class Critique(StrictOutput):
    summary: str = Field(min_length=5, max_length=1000)
    issues: list[CriticIssue] = Field(max_length=12)
    strengths: list[str] = Field(max_length=5)


def check_critique_quotes(critique: Critique, draft: Any) -> None:
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)

    texts = list(strings(draft))
    if any(not any(issue.draft_quote in text for text in texts) for issue in critique.issues):
        raise CreativeError("评审指出了草稿中不存在的原句，未采用这份评审。")


def evidence_readiness(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """A minimum material gate, not a promise that a particular story is supported."""
    story_predicates = {
        "genre.primary",
        "world.setting",
        "world.location",
        "faction.description",
        "character.identity",
        "character.affiliation",
        "character.ability",
        "gameplay.combat",
        "gameplay.exploration",
        "gameplay.vehicle",
        "gameplay.quest",
        "gameplay.multiplayer",
        "feature.description",
        "event.schedule",
        "update.change",
    }
    count = sum(fact["predicate"] in story_predicates for fact in facts)
    return {
        "ready": count > 0,
        "fact_count": len(facts),
        "story_fact_count": count,
        "reason": "ready" if count else "insufficient_story_evidence",
        "message": ""
        if count
        else (
            "当前知识版本只有名称、厂商等基础资料，缺少可讲述的游戏内容。"
            "请到知识步骤补充玩法、世界、角色或更新内容，发布新的知识版本，再创建营销任务。"
        ),
    }


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check_references(ids: list[str], evidence: list[dict[str, Any]]) -> None:
    allowed = {item["snapshot_member_id"] for item in evidence}
    if not set(ids).issubset(allowed):
        raise CreativeError("模型引用了冻结知识版本之外的证据，请重新生成。")


def assemble_script(draft: ScriptDraft, context: dict[str, Any]) -> dict[str, Any]:
    """The model cannot choose lineage, platform, duration, or time boundaries."""
    result = deepcopy(context["skeleton"])
    result.update(title=draft.title, caption=draft.caption, hashtags=draft.hashtags)
    if any(not re.fullmatch(r"#[\w]{1,60}", tag) for tag in draft.hashtags):
        raise CreativeError("模型返回的标签格式不正确。")
    duration = result["duration_seconds"]
    # A short opening, enough time for proof, and one CTA, not five equal-length slots.
    cuts = [
        0,
        round(duration * 0.1),
        round(duration * 0.25),
        round(duration * 0.6),
        round(duration * 0.85),
        duration,
    ]
    for index, beat in enumerate(draft.beats):
        check_references(beat.knowledge_member_ids, context["facts"])
        result["sections"][index].update(
            **beat.model_dump(),
            start_second=cuts[index],
            end_second=cuts[index + 1],
            purpose=PURPOSES[index],
            trend_signal_ids=[context["trend"]["id"]],
        )
    return result


def readiness_report(content: dict[str, Any]) -> dict[str, Any]:
    """Mechanical checks, not a claim about semantic truth or marketing performance."""
    sections = content["sections"]
    words = [len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", s["voiceover"])) for s in sections]
    duration = content["duration_seconds"]
    wpm = round(sum(words) * 60 / duration)
    issues: list[str] = []
    checks = {
        "spoken_pacing": (90 <= wpm <= 190, 25),
        "beat_pacing": (
            all(
                n <= (s["end_second"] - s["start_second"]) * 3.5
                for s, n in zip(sections, words, strict=True)
            ),
            20,
        ),
        "evidence_coverage": (
            all(s["knowledge_member_ids"] for s in sections if s["purpose"] in {"proof", "payoff"}),
            25,
        ),
        "opening_and_cta": (
            sections[0]["purpose"] == "hook" and sections[-1]["purpose"] == "cta",
            15,
        ),
        "on_screen_readability": (
            all(len(s["on_screen_text"].split()) <= 12 for s in sections),
            15,
        ),
    }
    for name, (passed, _) in checks.items():
        if not passed:
            issues.append(name + "_failed")
    return {
        "score": sum(weight for passed, weight in checks.values() if passed),
        "dimensions": {
            name: {"score": weight if passed else 0, "max": weight}
            for name, (passed, weight) in checks.items()
        },
        "issues": issues,
        "word_count": sum(words),
        "words_per_minute": wpm,
        "rule_version": RULE_VERSION,
    }
