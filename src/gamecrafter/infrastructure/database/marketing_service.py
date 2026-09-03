"""Zero-cost trend evidence, deterministic fit analysis, and human topic approval."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.agent_catalog import CAMPAIGN_STRATEGIST, TREND_ANALYST
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeSnapshotMemberRecord,
    KnowledgeSnapshotRecord,
    MarketingTaskRecord,
    ProjectRecord,
    TopicCandidateRecord,
    TopicReviewRecord,
    TrendSignalRecord,
)

FIT_RULE_VERSION = "trend-fit-v1"
TREND_PROCESSING_VERSION = "trend-processing-v1"
STRATEGY_BRIEF_VERSION = "marketing-strategy-brief-v1"
_TOKEN_PATTERN = re.compile(r"[\w#]+", re.UNICODE)


class MarketingServiceNotFoundError(LookupError):
    """Raised when a project, snapshot, task, or candidate does not exist."""


class MarketingServiceConflictError(RuntimeError):
    """Raised when immutable lineage or a human gate would be violated."""


class DatabaseMarketingService:
    """Persist user-verified trends and explainable, non-model topic decisions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_task(
        self,
        *,
        project_id: UUID,
        knowledge_snapshot_id: UUID,
        platform: str,
        markets: list[str],
        audience: str,
        goal: str,
        output_language: str,
        duration_seconds: int,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        clean = {
            "platform": self._text(platform, "platform", 80),
            "markets": self._markets(markets),
            "audience": self._text(audience, "audience", 500),
            "goal": self._text(goal, "goal", 500),
            "output_language": self._text(output_language, "output language", 40),
            "actor_id": self._text(actor_id, "actor", 120),
            "command_key": self._command_key(command_key),
        }
        if not 5 <= duration_seconds <= 180:
            raise MarketingServiceConflictError("duration must be between 5 and 180 seconds")
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            snapshot = session.scalar(
                select(KnowledgeSnapshotRecord).where(
                    KnowledgeSnapshotRecord.id == knowledge_snapshot_id,
                    KnowledgeSnapshotRecord.project_id == project_id,
                )
            )
            if snapshot is None:
                raise MarketingServiceNotFoundError("published knowledge snapshot not found")
            existing = session.scalar(
                select(MarketingTaskRecord).where(
                    MarketingTaskRecord.project_id == project_id,
                    MarketingTaskRecord.command_key == clean["command_key"],
                )
            )
            expected = (
                knowledge_snapshot_id,
                clean["platform"],
                clean["markets"],
                clean["audience"],
                clean["goal"],
                clean["output_language"],
                duration_seconds,
                clean["actor_id"],
            )
            if existing is not None:
                actual = (
                    existing.knowledge_snapshot_id,
                    existing.platform,
                    list(existing.markets),
                    existing.audience,
                    existing.goal,
                    existing.output_language,
                    existing.duration_seconds,
                    existing.created_by,
                )
                if actual != expected:
                    raise MarketingServiceConflictError(
                        "idempotency key was already used for a different marketing task"
                    )
                task_id = existing.id
                created = False
            else:
                task = MarketingTaskRecord(
                    project_id=project_id,
                    knowledge_snapshot_id=knowledge_snapshot_id,
                    platform=str(clean["platform"]),
                    markets=list(clean["markets"]),
                    audience=str(clean["audience"]),
                    goal=str(clean["goal"]),
                    output_language=str(clean["output_language"]),
                    duration_seconds=duration_seconds,
                    created_by=str(clean["actor_id"]),
                    command_key=str(clean["command_key"]),
                )
                session.add(task)
                session.flush()
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="marketing.task_created",
                        actor_type="human",
                        actor_id=str(clean["actor_id"]),
                        payload={
                            "task_id": str(task.id),
                            "knowledge_snapshot_id": str(knowledge_snapshot_id),
                            "platform": task.platform,
                            "markets": task.markets,
                            "duration_seconds": duration_seconds,
                        },
                    )
                )
                task_id = task.id
                created = True
        return self.get_task(project_id=project_id, task_id=task_id), created

    def list_tasks(self, project_id: UUID) -> list[dict[str, object]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            tasks = list(
                session.scalars(
                    select(MarketingTaskRecord)
                    .where(MarketingTaskRecord.project_id == project_id)
                    .order_by(MarketingTaskRecord.created_at.desc(), MarketingTaskRecord.id.desc())
                )
            )
            return [self._task(session, item) for item in tasks]

    def get_task(self, *, project_id: UUID, task_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            task = self._require_task(session, project_id, task_id)
            return self._task(session, task)

    def add_signal(
        self,
        *,
        project_id: UUID,
        source_name: str,
        source_url: str,
        observed_at: datetime,
        region: str,
        signal_type: str,
        title: str,
        keywords: list[str],
        metric_name: str | None,
        metric_value: float | None,
        notes: str | None,
        actor_id: str,
        command_key: str,
        actor_type: str = "human",
    ) -> tuple[dict[str, object], bool]:
        clean_url = self._https_url(source_url)
        clean_observed = self._aware_utc(observed_at)
        if signal_type not in {"hashtag", "sound", "topic", "search"}:
            raise MarketingServiceConflictError("unsupported trend signal type")
        if actor_type not in {"human", "system", "model"}:
            raise MarketingServiceConflictError("unsupported trend signal actor type")
        if metric_value is not None and (metric_value < 0 or metric_value > 10**15):
            raise MarketingServiceConflictError("trend metric must be between 0 and 10^15")
        clean_keywords = self._keywords(keywords)
        clean_metric_name = self._optional_text(metric_name, "metric name", 120)
        if (clean_metric_name is None) != (metric_value is None):
            raise MarketingServiceConflictError(
                "metric name and metric value must be provided together"
            )
        values = {
            "source_name": self._text(source_name, "source name", 160),
            "source_url": clean_url,
            "region": self._text(region, "region", 80).upper(),
            "title": self._text(title, "trend title", 300),
            "notes": self._optional_text(notes, "notes", 1000),
            "actor_id": self._text(actor_id, "actor", 120),
            "command_key": self._command_key(command_key),
        }
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            existing = session.scalar(
                select(TrendSignalRecord).where(
                    TrendSignalRecord.project_id == project_id,
                    TrendSignalRecord.command_key == values["command_key"],
                )
            )
            expected = (
                values["source_name"],
                values["source_url"],
                clean_observed,
                values["region"],
                signal_type,
                values["title"],
                clean_keywords,
                clean_metric_name,
                Decimal(str(metric_value)) if metric_value is not None else None,
                values["notes"],
                values["actor_id"],
            )
            if existing is not None:
                actual = (
                    existing.source_name,
                    existing.source_url,
                    self._stored_utc(existing.observed_at),
                    existing.region,
                    existing.signal_type,
                    existing.title,
                    list(existing.keywords),
                    existing.metric_name,
                    Decimal(str(existing.metric_value))
                    if existing.metric_value is not None
                    else None,
                    existing.notes,
                    existing.created_by,
                )
                if actual != expected:
                    raise MarketingServiceConflictError(
                        "idempotency key was already used for a different trend signal"
                    )
                signal_id = existing.id
                created = False
            else:
                signal = TrendSignalRecord(
                    project_id=project_id,
                    source_name=str(values["source_name"]),
                    source_url=str(values["source_url"]),
                    observed_at=clean_observed,
                    region=str(values["region"]),
                    signal_type=signal_type,
                    title=str(values["title"]),
                    keywords=clean_keywords,
                    metric_name=clean_metric_name,
                    metric_value=metric_value,
                    notes=values["notes"],
                    created_by=str(values["actor_id"]),
                    command_key=str(values["command_key"]),
                )
                session.add(signal)
                session.flush()
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="trend.signal_recorded",
                        actor_type=actor_type,
                        actor_id=str(values["actor_id"]),
                        payload={
                            "trend_signal_id": str(signal.id),
                            "source_name": signal.source_name,
                            "region": signal.region,
                            "signal_type": signal.signal_type,
                            "observed_at": clean_observed.isoformat(),
                        },
                    )
                )
                signal_id = signal.id
                created = True
        return self.get_signal(project_id=project_id, signal_id=signal_id), created

    def list_signals(self, project_id: UUID) -> list[dict[str, object]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            signals = list(
                session.scalars(
                    select(TrendSignalRecord)
                    .where(TrendSignalRecord.project_id == project_id)
                    .order_by(TrendSignalRecord.observed_at.desc(), TrendSignalRecord.id.desc())
                )
            )
            return self._processed_signals(signals)

    def get_signal(self, *, project_id: UUID, signal_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            signal = session.scalar(
                select(TrendSignalRecord).where(
                    TrendSignalRecord.id == signal_id,
                    TrendSignalRecord.project_id == project_id,
                )
            )
            if signal is None:
                raise MarketingServiceNotFoundError("trend signal not found")
            return self._processed_signals([signal])[0]

    def analyze(self, *, project_id: UUID, task_id: UUID, actor_id: str) -> list[dict[str, object]]:
        self._text(actor_id, "actor", 120)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            task = self._require_task(session, project_id, task_id)
            snapshot = session.get(KnowledgeSnapshotRecord, task.knowledge_snapshot_id)
            if snapshot is None:
                raise MarketingServiceConflictError("task knowledge snapshot lineage is missing")
            members = list(
                session.scalars(
                    select(KnowledgeSnapshotMemberRecord).where(
                        KnowledgeSnapshotMemberRecord.snapshot_id == snapshot.id
                    )
                )
            )
            if not members:
                raise MarketingServiceConflictError("task knowledge snapshot is empty")
            signals = list(
                session.scalars(
                    select(TrendSignalRecord).where(TrendSignalRecord.project_id == project_id)
                )
            )
            if not signals:
                raise MarketingServiceConflictError(
                    "record at least one trend signal before analysis"
                )
            created_count = 0
            for signal in signals:
                existing = session.scalar(
                    select(TopicCandidateRecord).where(
                        TopicCandidateRecord.task_id == task.id,
                        TopicCandidateRecord.trend_signal_id == signal.id,
                    )
                )
                if existing is not None:
                    continue
                analysis = self._fit(session, task, members, signal)
                session.add(
                    TopicCandidateRecord(task_id=task.id, trend_signal_id=signal.id, **analysis)
                )
                created_count += 1
            session.flush()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="marketing.topic_fit_analyzed",
                    actor_type="system",
                    actor_id=TREND_ANALYST.key,
                    payload={
                        "task_id": str(task.id),
                        "rule_version": FIT_RULE_VERSION,
                        "signal_count": len(signals),
                        "created_candidate_count": created_count,
                        "model_used": False,
                        "agent_version": TREND_ANALYST.version,
                        "agent_mode": TREND_ANALYST.mode.value,
                    },
                )
            )
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="marketing.campaign_strategy_proposed",
                    actor_type="system",
                    actor_id=CAMPAIGN_STRATEGIST.key,
                    payload={
                        "task_id": str(task.id),
                        "candidate_count": created_count,
                        "agent_version": CAMPAIGN_STRATEGIST.version,
                        "agent_mode": CAMPAIGN_STRATEGIST.mode.value,
                        "human_topic_gate_required": True,
                    },
                )
            )
        return self.list_candidates(project_id=project_id, task_id=task_id)

    def list_candidates(self, *, project_id: UUID, task_id: UUID) -> list[dict[str, object]]:
        with self._session_factory() as session:
            self._require_task(session, project_id, task_id)
            candidates = list(
                session.scalars(
                    select(TopicCandidateRecord)
                    .where(TopicCandidateRecord.task_id == task_id)
                    .order_by(TopicCandidateRecord.score.desc(), TopicCandidateRecord.id)
                )
            )
            reviews = list(
                session.scalars(
                    select(TopicReviewRecord)
                    .where(TopicReviewRecord.task_id == task_id)
                    .order_by(TopicReviewRecord.created_at, TopicReviewRecord.id)
                )
            )
            history: dict[UUID, list[TopicReviewRecord]] = {}
            for review in reviews:
                history.setdefault(review.candidate_id, []).append(review)
            return [self._candidate(session, item, history.get(item.id, [])) for item in candidates]

    def get_strategy_brief(self, *, project_id: UUID, task_id: UUID) -> dict[str, object]:
        """Project the ranked evidence into one readable, deterministic campaign recommendation."""
        with self._session_factory() as session:
            task = self._require_task(session, project_id, task_id)
            candidates = list(
                session.scalars(
                    select(TopicCandidateRecord)
                    .where(TopicCandidateRecord.task_id == task.id)
                    .order_by(TopicCandidateRecord.score.desc(), TopicCandidateRecord.id)
                )
            )
            if not candidates:
                raise MarketingServiceConflictError(
                    "run topic analysis before requesting a strategy brief"
                )
            latest_reviews: dict[UUID, TopicReviewRecord] = {}
            for review in session.scalars(
                select(TopicReviewRecord)
                .where(TopicReviewRecord.task_id == task.id)
                .order_by(TopicReviewRecord.created_at, TopicReviewRecord.id)
            ):
                latest_reviews[review.candidate_id] = review
            approved_id = next(
                (
                    candidate_id
                    for candidate_id, review in latest_reviews.items()
                    if review.decision == "approve"
                ),
                None,
            )
            chosen = next(
                (candidate for candidate in candidates if candidate.id == approved_id),
                candidates[0],
            )
            signal = session.get(TrendSignalRecord, chosen.trend_signal_id)
            if signal is None:
                raise MarketingServiceConflictError("strategy trend lineage is missing")
            snapshot = session.get(KnowledgeSnapshotRecord, task.knowledge_snapshot_id)
            if snapshot is None:
                raise MarketingServiceConflictError("strategy snapshot lineage is missing")
            matched_ids = set(chosen.matched_snapshot_member_ids)
            facts: list[dict[str, object]] = []
            for member in session.scalars(
                select(KnowledgeSnapshotMemberRecord)
                .where(KnowledgeSnapshotMemberRecord.snapshot_id == snapshot.id)
                .order_by(KnowledgeSnapshotMemberRecord.id)
            ):
                claim = session.get(KnowledgeClaimRecord, member.claim_id)
                review = session.get(ClaimReviewRecord, member.review_id)
                if claim is None or review is None:
                    raise MarketingServiceConflictError("strategy fact lineage is incomplete")
                facts.append(
                    {
                        "snapshot_member_id": str(member.id),
                        "predicate": claim.predicate,
                        "value": review.approved_value
                        if review.approved_value is not None
                        else claim.value,
                        "matched_to_trend": str(member.id) in matched_ids,
                    }
                )
            facts.sort(
                key=lambda item: (not bool(item["matched_to_trend"]), str(item["predicate"]))
            )
            proof_facts = facts[:3]
            game_name = next(
                (str(item["value"]) for item in facts if item["predicate"] == "game.name"),
                "the game",
            )
            direction_key = self._direction_key([str(item["predicate"]) for item in proof_facts])
            duration = task.duration_seconds
            hook_end = max(2, round(duration * 0.13))
            proof_end = max(hook_end + 1, round(duration * 0.67))
            payoff_end = max(proof_end + 1, round(duration * 0.87))
            chosen_payload = self._candidate(
                session,
                chosen,
                [latest_reviews[chosen.id]] if chosen.id in latest_reviews else [],
            )
            review = latest_reviews.get(chosen.id)
            return {
                "schema_version": STRATEGY_BRIEF_VERSION,
                "status": "approved" if approved_id == chosen.id else "draft",
                "candidate_id": str(chosen.id),
                "direction_key": direction_key,
                "game_name": game_name,
                "marketing_direction": chosen.angle,
                "recommended_topic": chosen.hook,
                "core_message": (
                    f"Use the verified {signal.title} signal as the entry point, then earn "
                    f"interest in {game_name} with approved knowledge instead of "
                    "unsupported claims."
                ),
                "audience": task.audience,
                "goal": task.goal,
                "platform": task.platform,
                "markets": list(task.markets),
                "output_language": task.output_language,
                "duration_seconds": duration,
                "fit_score": chosen.score,
                "why_this_direction": chosen.rationale,
                "execution_plan": [
                    {
                        "key": "hook",
                        "start_second": 0,
                        "end_second": hook_end,
                        "guidance": chosen.hook,
                    },
                    {
                        "key": "proof",
                        "start_second": hook_end,
                        "end_second": proof_end,
                        "guidance": (
                            "Show one to three approved game facts that make the trend "
                            "connection credible."
                        ),
                    },
                    {
                        "key": "payoff",
                        "start_second": proof_end,
                        "end_second": payoff_end,
                        "guidance": (
                            "Resolve the hook with the strongest visual or gameplay proof "
                            "available."
                        ),
                    },
                    {
                        "key": "cta",
                        "start_second": payoff_end,
                        "end_second": duration,
                        "guidance": (
                            "Ask viewers which part of the game they want to discover next."
                        ),
                    },
                ],
                "proof_facts": proof_facts,
                "trend_evidence": {
                    "title": signal.title,
                    "source_name": signal.source_name,
                    "source_url": signal.source_url,
                    "observed_at": self._stored_utc(signal.observed_at).isoformat(),
                    "region": signal.region,
                    "metric_name": signal.metric_name,
                    "metric_value": (
                        float(signal.metric_value) if signal.metric_value is not None else None
                    ),
                },
                "knowledge_snapshot": {
                    "id": str(snapshot.id),
                    "version_number": snapshot.version_number,
                    "proof_fact_count": len(proof_facts),
                },
                "risks": list(chosen.risks),
                "human_decision": (
                    {
                        "decision": review.decision,
                        "reason": review.reason,
                        "reviewer_id": review.reviewer_id,
                        "created_at": self._stored_utc(review.created_at).isoformat(),
                    }
                    if review is not None
                    else None
                ),
                "alternatives": [
                    {
                        "candidate_id": str(candidate.id),
                        "topic": candidate.hook,
                        "direction": candidate.angle,
                        "fit_score": candidate.score,
                    }
                    for candidate in candidates
                    if candidate.id != chosen.id
                ][:2],
                "agent": {
                    "key": CAMPAIGN_STRATEGIST.key,
                    "version": CAMPAIGN_STRATEGIST.version,
                    "mode": CAMPAIGN_STRATEGIST.mode.value,
                    "model_used": False,
                },
                "candidate": chosen_payload,
            }

    @staticmethod
    def _direction_key(predicates: list[str]) -> str:
        joined = " ".join(predicates)
        if "character." in joined:
            return "character_trend_crossover"
        if any(prefix in joined for prefix in ("gameplay.", "feature.", "system.")):
            return "gameplay_proof"
        if any(prefix in joined for prefix in ("world.", "lore.", "location.", "genre.")):
            return "world_discovery"
        return "trend_led_discovery"

    def review_topic(
        self,
        *,
        project_id: UUID,
        task_id: UUID,
        candidate_id: UUID,
        decision: str,
        reason: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        if decision not in {"approve", "reject", "defer"}:
            raise MarketingServiceConflictError("unsupported topic decision")
        clean_reason = self._text(reason, "decision reason", 1000)
        clean_actor = self._text(actor_id, "reviewer", 120)
        clean_key = self._command_key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            task = self._require_task(session, project_id, task_id)
            candidate = session.scalar(
                select(TopicCandidateRecord).where(
                    TopicCandidateRecord.id == candidate_id,
                    TopicCandidateRecord.task_id == task.id,
                )
            )
            if candidate is None:
                raise MarketingServiceNotFoundError("topic candidate not found")
            existing = session.scalar(
                select(TopicReviewRecord).where(
                    TopicReviewRecord.task_id == task.id,
                    TopicReviewRecord.command_key == clean_key,
                )
            )
            if existing is not None:
                if (
                    existing.candidate_id != candidate.id
                    or existing.decision != decision
                    or existing.reason != clean_reason
                    or existing.reviewer_id != clean_actor
                ):
                    raise MarketingServiceConflictError(
                        "idempotency key was already used for a different topic decision"
                    )
                review_id = existing.id
                created = False
            else:
                if decision == "approve":
                    latest: dict[UUID, TopicReviewRecord] = {}
                    for item in session.scalars(
                        select(TopicReviewRecord)
                        .where(TopicReviewRecord.task_id == task.id)
                        .order_by(TopicReviewRecord.created_at, TopicReviewRecord.id)
                    ):
                        latest[item.candidate_id] = item
                    if any(
                        item.candidate_id != candidate.id and item.decision == "approve"
                        for item in latest.values()
                    ):
                        raise MarketingServiceConflictError(
                            "reject the currently approved topic before approving another"
                        )
                review = TopicReviewRecord(
                    task_id=task.id,
                    candidate_id=candidate.id,
                    decision=decision,
                    reason=clean_reason,
                    reviewer_id=clean_actor,
                    command_key=clean_key,
                )
                session.add(review)
                session.flush()
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="marketing.topic_reviewed",
                        actor_type="human",
                        actor_id=clean_actor,
                        payload={
                            "task_id": str(task.id),
                            "candidate_id": str(candidate.id),
                            "review_id": str(review.id),
                            "decision": decision,
                        },
                    )
                )
                review_id = review.id
                created = True
        with self._session_factory() as session:
            review = session.get(TopicReviewRecord, review_id)
            assert review is not None
            return self._review(review), created

    def _fit(
        self,
        session: Session,
        task: MarketingTaskRecord,
        members: list[KnowledgeSnapshotMemberRecord],
        signal: TrendSignalRecord,
    ) -> dict[str, object]:
        # The signal can be recorded after task creation. Compare the observation with its own
        # immutable record time, which also prevents later analysis runs from changing freshness.
        reference_time = self._stored_utc(signal.created_at)
        age_days = max(0, (reference_time - self._stored_utc(signal.observed_at)).days)
        future = self._stored_utc(signal.observed_at) > reference_time
        freshness = (
            0
            if future
            else 25
            if age_days <= 7
            else 18
            if age_days <= 30
            else 10
            if age_days <= 90
            else 4
        )
        region = 25 if signal.region == "GLOBAL" or signal.region in task.markets else 8
        evidence = 25 if signal.metric_name is not None and signal.metric_value is not None else 14
        signal_tokens = self._tokens(" ".join([signal.title, *signal.keywords]))
        matched: list[str] = []
        game_name = "the game"
        for member in members:
            claim = session.get(KnowledgeClaimRecord, member.claim_id)
            review = session.get(ClaimReviewRecord, member.review_id)
            if claim is None or review is None:
                raise MarketingServiceConflictError("snapshot member lineage is incomplete")
            if claim.predicate == "game.name" and review.approved_value is not None:
                game_name = str(review.approved_value)
            knowledge_tokens = self._tokens(
                str(review.approved_normalized_value or review.approved_value)
            )
            if signal_tokens.intersection(knowledge_tokens):
                matched.append(str(member.id))
        relevance = 25 if matched else 8
        risks: list[str] = ["manual_source_observation_not_independently_verified"]
        if future:
            risks.append("observation_time_after_task_creation")
        elif age_days > 30:
            risks.append("stale_signal")
        if region < 25:
            risks.append("market_region_mismatch")
        if not matched:
            risks.append("no_lexical_knowledge_match")
        score = freshness + region + evidence + relevance
        return {
            "score": score,
            "dimensions": {
                "freshness": {"score": freshness, "max": 25, "age_days": age_days},
                "market_alignment": {"score": region, "max": 25, "signal_region": signal.region},
                "source_completeness": {
                    "score": evidence,
                    "max": 25,
                    "has_metric": signal.metric_value is not None,
                },
                "knowledge_relevance": {
                    "score": relevance,
                    "max": 25,
                    "matched_member_count": len(matched),
                },
            },
            "matched_snapshot_member_ids": matched,
            "angle": (
                f"Use the verified “{signal.title}” signal as a {task.platform} angle "
                f"for {game_name}."
            ),
            "hook": f"What if “{signal.title}” happened inside {game_name}?",
            "rationale": (
                f"Deterministic {FIT_RULE_VERSION} score {score}/100: freshness {freshness}/25, "
                f"market alignment {region}/25, source completeness {evidence}/25, and "
                f"knowledge relevance {relevance}/25. No model was used."
            ),
            "risks": risks,
            "rule_version": FIT_RULE_VERSION,
        }

    def _task(self, session: Session, task: MarketingTaskRecord) -> dict[str, object]:
        snapshot = session.get(KnowledgeSnapshotRecord, task.knowledge_snapshot_id)
        if snapshot is None:
            raise MarketingServiceConflictError("marketing task snapshot lineage is missing")
        candidate_count = len(
            list(
                session.scalars(
                    select(TopicCandidateRecord.id).where(TopicCandidateRecord.task_id == task.id)
                )
            )
        )
        latest: dict[UUID, TopicReviewRecord] = {}
        for review in session.scalars(
            select(TopicReviewRecord)
            .where(TopicReviewRecord.task_id == task.id)
            .order_by(TopicReviewRecord.created_at, TopicReviewRecord.id)
        ):
            latest[review.candidate_id] = review
        approved = next((item for item in latest.values() if item.decision == "approve"), None)
        return {
            "id": str(task.id),
            "project_id": str(task.project_id),
            "knowledge_snapshot_id": str(task.knowledge_snapshot_id),
            "knowledge_snapshot_version": snapshot.version_number,
            "platform": task.platform,
            "markets": list(task.markets),
            "audience": task.audience,
            "goal": task.goal,
            "output_language": task.output_language,
            "duration_seconds": task.duration_seconds,
            "candidate_count": candidate_count,
            "approved_candidate_id": str(approved.candidate_id) if approved else None,
            "created_by": task.created_by,
            "created_at": self._stored_utc(task.created_at).isoformat(),
        }

    def _candidate(
        self,
        session: Session,
        item: TopicCandidateRecord,
        reviews: list[TopicReviewRecord],
    ) -> dict[str, object]:
        signal = session.get(TrendSignalRecord, item.trend_signal_id)
        if signal is None:
            raise MarketingServiceConflictError("topic candidate trend lineage is missing")
        return {
            "id": str(item.id),
            "task_id": str(item.task_id),
            "trend_signal": self._signal(signal),
            "score": item.score,
            "dimensions": dict(item.dimensions),
            "matched_snapshot_member_ids": list(item.matched_snapshot_member_ids),
            "angle": item.angle,
            "hook": item.hook,
            "rationale": item.rationale,
            "risks": list(item.risks),
            "rule_version": item.rule_version,
            "status": reviews[-1].decision if reviews else "unreviewed",
            "review_history": [self._review(review) for review in reviews],
            "created_at": self._stored_utc(item.created_at).isoformat(),
        }

    @classmethod
    def _signal(
        cls, item: TrendSignalRecord, processing: dict[str, object] | None = None
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "id": str(item.id),
            "project_id": str(item.project_id),
            "source_name": item.source_name,
            "source_url": item.source_url,
            "observed_at": DatabaseMarketingService._stored_utc(item.observed_at).isoformat(),
            "region": item.region,
            "signal_type": item.signal_type,
            "title": item.title,
            "keywords": list(item.keywords),
            "metric_name": item.metric_name,
            "metric_value": float(item.metric_value) if item.metric_value is not None else None,
            "notes": item.notes,
            "created_by": item.created_by,
            "created_at": DatabaseMarketingService._stored_utc(item.created_at).isoformat(),
        }
        result["processing"] = processing or cls._processing(item)
        return result

    @classmethod
    def _processed_signals(cls, signals: list[TrendSignalRecord]) -> list[dict[str, object]]:
        ordered = sorted(signals, key=lambda item: (cls._stored_utc(item.observed_at), item.id))
        fingerprints: dict[str, UUID] = {}
        clusters: list[dict[str, object]] = []
        processing_by_id: dict[UUID, dict[str, object]] = {}
        for item in ordered:
            normalized = cls._normalize_trend_title(item.title)
            fingerprint = hashlib.sha256(
                f"{item.region}|{item.signal_type}|{normalized}".encode()
            ).hexdigest()
            duplicate_of = fingerprints.get(fingerprint)
            if duplicate_of is None:
                fingerprints[fingerprint] = item.id
            tokens = cls._tokens(normalized)
            cluster = next(
                (
                    candidate
                    for candidate in clusters
                    if candidate["region"] == item.region
                    and candidate["signal_type"] == item.signal_type
                    and cls._jaccard(tokens, candidate["tokens"]) >= 0.5
                ),
                None,
            )
            if cluster is None:
                cluster = {
                    "key": hashlib.sha256(
                        f"{item.region}|{item.signal_type}|{normalized}".encode()
                    ).hexdigest()[:16],
                    "region": item.region,
                    "signal_type": item.signal_type,
                    "tokens": tokens,
                    "members": [],
                }
                clusters.append(cluster)
            cluster["members"].append(item.id)
            processing_by_id[item.id] = {
                "version": TREND_PROCESSING_VERSION,
                "normalized_title": normalized,
                "content_fingerprint_sha256": fingerprint,
                "duplicate_of_signal_id": str(duplicate_of) if duplicate_of else None,
                "cluster_key": cluster["key"],
                "cluster_size": 0,
                "freshness": cls._freshness(item.observed_at),
            }
        for cluster in clusters:
            size = len(cluster["members"])
            for signal_id in cluster["members"]:
                processing_by_id[signal_id]["cluster_size"] = size
        return [cls._signal(item, processing_by_id[item.id]) for item in signals]

    @classmethod
    def _processing(cls, item: TrendSignalRecord) -> dict[str, object]:
        normalized = cls._normalize_trend_title(item.title)
        fingerprint = hashlib.sha256(
            f"{item.region}|{item.signal_type}|{normalized}".encode()
        ).hexdigest()
        return {
            "version": TREND_PROCESSING_VERSION,
            "normalized_title": normalized,
            "content_fingerprint_sha256": fingerprint,
            "duplicate_of_signal_id": None,
            "cluster_key": fingerprint[:16],
            "cluster_size": 1,
            "freshness": cls._freshness(item.observed_at),
        }

    @staticmethod
    def _normalize_trend_title(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold().replace("#", " ")
        return " ".join(_TOKEN_PATTERN.findall(normalized))

    @staticmethod
    def _jaccard(left: set[str], right: object) -> float:
        right_tokens = right if isinstance(right, set) else set()
        if not left or not right_tokens:
            return 0.0
        return len(left & right_tokens) / len(left | right_tokens)

    @classmethod
    def _freshness(cls, observed_at: datetime) -> str:
        age_days = max(0, (datetime.now(UTC) - cls._stored_utc(observed_at)).days)
        if age_days <= 7:
            return "fresh"
        if age_days <= 30:
            return "aging"
        return "stale"

    @staticmethod
    def _review(item: TopicReviewRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "task_id": str(item.task_id),
            "candidate_id": str(item.candidate_id),
            "decision": item.decision,
            "reason": item.reason,
            "reviewer_id": item.reviewer_id,
            "created_at": DatabaseMarketingService._stored_utc(item.created_at).isoformat(),
        }

    @staticmethod
    def _require_project(session: Session, project_id: UUID) -> ProjectRecord:
        project = session.get(ProjectRecord, project_id)
        if project is None:
            raise MarketingServiceNotFoundError("project not found")
        return project

    @classmethod
    def _lock_project(cls, session: Session, project_id: UUID) -> ProjectRecord:
        project = session.scalar(
            select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update()
        )
        if project is None:
            raise MarketingServiceNotFoundError("project not found")
        return project

    @staticmethod
    def _require_task(session: Session, project_id: UUID, task_id: UUID) -> MarketingTaskRecord:
        task = session.scalar(
            select(MarketingTaskRecord).where(
                MarketingTaskRecord.id == task_id,
                MarketingTaskRecord.project_id == project_id,
            )
        )
        if task is None:
            raise MarketingServiceNotFoundError("marketing task not found")
        return task

    @staticmethod
    def _text(value: str, label: str, maximum: int) -> str:
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise MarketingServiceConflictError(f"{label} must contain 1 to {maximum} characters")
        return clean

    @classmethod
    def _optional_text(cls, value: str | None, label: str, maximum: int) -> str | None:
        if value is None or not value.strip():
            return None
        return cls._text(value, label, maximum)

    @classmethod
    def _command_key(cls, value: str) -> str:
        clean = cls._text(value, "idempotency key", 160)
        if len(clean) < 8:
            raise MarketingServiceConflictError("idempotency key must contain 8 to 160 characters")
        return clean

    @classmethod
    def _markets(cls, values: list[str]) -> list[str]:
        cleaned = sorted({cls._text(value, "market", 80).upper() for value in values})
        if not cleaned or len(cleaned) > 20:
            raise MarketingServiceConflictError("markets must contain 1 to 20 unique values")
        return cleaned

    @classmethod
    def _keywords(cls, values: list[str]) -> list[str]:
        cleaned = sorted({cls._text(value, "keyword", 80) for value in values}, key=str.casefold)
        if len(cleaned) > 30:
            raise MarketingServiceConflictError("trend keywords cannot exceed 30 values")
        return cleaned

    @staticmethod
    def _https_url(value: str) -> str:
        clean = value.strip()
        parsed = urlsplit(clean)
        if len(clean) > 2048 or parsed.scheme.lower() != "https" or not parsed.hostname:
            raise MarketingServiceConflictError("trend source URL must be an absolute HTTPS URL")
        if parsed.username or parsed.password:
            raise MarketingServiceConflictError("trend source URL cannot contain credentials")
        return clean

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise MarketingServiceConflictError("timestamp must include a timezone")
        return value.astimezone(UTC)

    @staticmethod
    def _stored_utc(value: datetime) -> datetime:
        """Restore UTC for SQLite, whose DateTime adapter drops timezone metadata."""

        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token.casefold() for token in _TOKEN_PATTERN.findall(value) if len(token) >= 2}
