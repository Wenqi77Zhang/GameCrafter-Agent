"""Deterministic, evidence-bound TikTok script workflow with bounded revision."""

# ruff: noqa: E501

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeSnapshotMemberRecord,
    MarketingTaskRecord,
    ProjectRecord,
    ScriptEvaluationRecord,
    ScriptExportRecord,
    ScriptFinalReviewRecord,
    ScriptRunRecord,
    ScriptVersionRecord,
    TopicCandidateRecord,
    TopicReviewRecord,
    TrendSignalRecord,
)

GENERATOR_VERSION = "tiktok-template-v1"
EVALUATOR_VERSION = "script-quality-v1"
SCHEMA_VERSION = "tiktok-script-v1"
MAX_CONTENT_BYTES = 65_536


class ScriptServiceNotFoundError(LookupError):
    """Raised when workflow lineage is absent."""


class ScriptServiceConflictError(RuntimeError):
    """Raised when a gate, budget, or immutable lineage would be violated."""


class DatabaseScriptService:
    """Create evidence-safe script versions and append-only quality decisions."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_run(
        self,
        *,
        project_id: UUID,
        marketing_task_id: UUID,
        revision_budget: int,
        score_threshold: int,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        if not 0 <= revision_budget <= 5:
            raise ScriptServiceConflictError("revision budget must be between 0 and 5")
        if not 1 <= score_threshold <= 100:
            raise ScriptServiceConflictError("score threshold must be between 1 and 100")
        actor = self._text(actor_id, "actor", 120)
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            task = self._require_task(session, project_id, marketing_task_id)
            if task.platform.casefold() != "tiktok" or task.output_language.casefold() not in {
                "en",
                "english",
            }:
                raise ScriptServiceConflictError(
                    "first release supports English TikTok script delivery only"
                )
            review = self._current_approved_review(session, task.id)
            candidate = session.get(TopicCandidateRecord, review.candidate_id)
            if candidate is None:
                raise ScriptServiceConflictError("approved topic lineage is incomplete")
            existing = session.scalar(
                select(ScriptRunRecord).where(
                    ScriptRunRecord.project_id == project_id,
                    ScriptRunRecord.command_key == key,
                )
            )
            expected = (
                task.id,
                candidate.id,
                review.id,
                task.knowledge_snapshot_id,
                revision_budget,
                score_threshold,
                actor,
            )
            if existing is not None:
                actual = (
                    existing.marketing_task_id,
                    existing.topic_candidate_id,
                    existing.topic_review_id,
                    existing.knowledge_snapshot_id,
                    existing.revision_budget,
                    existing.score_threshold,
                    existing.created_by,
                )
                if actual != expected:
                    raise ScriptServiceConflictError(
                        "idempotency key was already used for a different script run"
                    )
                run_id, created = existing.id, False
            else:
                run = ScriptRunRecord(
                    project_id=project_id,
                    marketing_task_id=task.id,
                    topic_candidate_id=candidate.id,
                    topic_review_id=review.id,
                    knowledge_snapshot_id=task.knowledge_snapshot_id,
                    revision_budget=revision_budget,
                    score_threshold=score_threshold,
                    generator_version=GENERATOR_VERSION,
                    evaluator_version=EVALUATOR_VERSION,
                    created_by=actor,
                    command_key=key,
                )
                session.add(run)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.run_created",
                    actor,
                    {"script_run_id": str(run.id), "topic_review_id": str(review.id)},
                )
                run_id, created = run.id, True
        return self.get_run(project_id=project_id, run_id=run_id), created

    def list_runs(self, project_id: UUID) -> list[dict[str, object]]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            records = list(
                session.scalars(
                    select(ScriptRunRecord)
                    .where(ScriptRunRecord.project_id == project_id)
                    .order_by(ScriptRunRecord.created_at.desc(), ScriptRunRecord.id.desc())
                )
            )
            return [self._run(session, item) for item in records]

    def get_run(self, *, project_id: UUID, run_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            return self._run(session, self._require_run(session, project_id, run_id))

    def generate(
        self, *, project_id: UUID, run_id: UUID, actor_id: str, command_key: str
    ) -> tuple[dict[str, object], bool]:
        return self._create_version(
            project_id=project_id,
            run_id=run_id,
            origin="generated",
            content=None,
            actor_id=actor_id,
            command_key=command_key,
        )

    def edit(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        content: dict[str, Any],
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        return self._create_version(
            project_id=project_id,
            run_id=run_id,
            origin="human_edit",
            content=content,
            actor_id=actor_id,
            command_key=command_key,
        )

    def _create_version(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        origin: str,
        content: dict[str, Any] | None,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        actor = self._text(actor_id, "actor", 120)
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            run = self._require_run(session, project_id, run_id)
            existing = session.scalar(
                select(ScriptVersionRecord).where(
                    ScriptVersionRecord.run_id == run.id,
                    ScriptVersionRecord.command_key == key,
                )
            )
            latest = self._latest_version(session, run.id)
            if existing is not None:
                expected_content = content if content is not None else self._template(session, run)
                normalized = self._validate_content(session, run, expected_content)
                if existing.origin != origin or existing.content_sha256 != self._digest(normalized):
                    raise ScriptServiceConflictError(
                        "idempotency key was already used for a different script version"
                    )
                version_id, created = existing.id, False
            else:
                if origin == "generated" and latest is not None:
                    raise ScriptServiceConflictError("initial script was already generated")
                if origin == "human_edit" and latest is None:
                    raise ScriptServiceConflictError("generate a script before editing it")
                normalized = self._validate_content(
                    session, run, content if content is not None else self._template(session, run)
                )
                version = ScriptVersionRecord(
                    run_id=run.id,
                    version_number=1 if latest is None else latest.version_number + 1,
                    parent_version_id=latest.id if latest else None,
                    origin=origin,
                    content=normalized,
                    content_sha256=self._digest(normalized),
                    created_by=actor,
                    command_key=key,
                )
                session.add(version)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.version_created",
                    actor,
                    {
                        "script_run_id": str(run.id),
                        "script_version_id": str(version.id),
                        "version_number": version.version_number,
                        "origin": origin,
                        "content_sha256": version.content_sha256,
                    },
                )
                version_id, created = version.id, True
        return self.get_version(
            project_id=project_id, run_id=run_id, version_id=version_id
        ), created

    def list_versions(self, *, project_id: UUID, run_id: UUID) -> list[dict[str, object]]:
        with self._session_factory() as session:
            run = self._require_run(session, project_id, run_id)
            items = list(
                session.scalars(
                    select(ScriptVersionRecord)
                    .where(ScriptVersionRecord.run_id == run.id)
                    .order_by(ScriptVersionRecord.version_number)
                )
            )
            return [self._version(item) for item in items]

    def get_version(self, *, project_id: UUID, run_id: UUID, version_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            self._require_run(session, project_id, run_id)
            return self._version(self._require_version(session, run_id, version_id))

    def evaluate(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            run = self._require_run(session, project_id, run_id)
            version = self._require_version(session, run.id, version_id)
            existing = session.scalar(
                select(ScriptEvaluationRecord).where(
                    ScriptEvaluationRecord.run_id == run.id,
                    ScriptEvaluationRecord.command_key == key,
                )
            )
            report = self._score(session, run, dict(version.content))
            if existing is not None:
                if existing.script_version_id != version.id:
                    raise ScriptServiceConflictError(
                        "idempotency key was already used for a different evaluation"
                    )
                evaluation_id, created = existing.id, False
            else:
                evaluation = ScriptEvaluationRecord(
                    run_id=run.id,
                    script_version_id=version.id,
                    score=report["score"],
                    passed=report["score"] >= run.score_threshold,
                    dimensions=report["dimensions"],
                    issues=report["issues"],
                    rule_version=run.evaluator_version,
                    command_key=key,
                )
                session.add(evaluation)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.evaluated",
                    "local-system",
                    {
                        "script_run_id": str(run.id),
                        "script_version_id": str(version.id),
                        "score": evaluation.score,
                        "passed": evaluation.passed,
                    },
                )
                evaluation_id, created = evaluation.id, True
        return self.get_evaluation(project_id, run_id, evaluation_id), created

    def get_evaluation(
        self, project_id: UUID, run_id: UUID, evaluation_id: UUID
    ) -> dict[str, object]:
        with self._session_factory() as session:
            self._require_run(session, project_id, run_id)
            item = session.scalar(
                select(ScriptEvaluationRecord).where(
                    ScriptEvaluationRecord.id == evaluation_id,
                    ScriptEvaluationRecord.run_id == run_id,
                )
            )
            if item is None:
                raise ScriptServiceNotFoundError("script evaluation not found")
            return self._evaluation(item)

    def revise(
        self, *, project_id: UUID, run_id: UUID, actor_id: str, command_key: str
    ) -> tuple[dict[str, object], bool]:
        actor = self._text(actor_id, "actor", 120)
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            run = self._require_run(session, project_id, run_id)
            existing = session.scalar(
                select(ScriptVersionRecord).where(
                    ScriptVersionRecord.run_id == run.id,
                    ScriptVersionRecord.command_key == key,
                )
            )
            if existing is not None:
                if existing.origin != "auto_revision":
                    raise ScriptServiceConflictError("idempotency key belongs to another version")
                version_id, created = existing.id, False
            else:
                latest = self._latest_version(session, run.id)
                if latest is None:
                    raise ScriptServiceConflictError("generate and evaluate a script first")
                evaluation = session.scalar(
                    select(ScriptEvaluationRecord)
                    .where(ScriptEvaluationRecord.script_version_id == latest.id)
                    .order_by(
                        ScriptEvaluationRecord.created_at.desc(), ScriptEvaluationRecord.id.desc()
                    )
                )
                if evaluation is None:
                    raise ScriptServiceConflictError("evaluate the latest version before revision")
                if evaluation.passed:
                    raise ScriptServiceConflictError("latest version already passes evaluation")
                used = (
                    session.scalar(
                        select(func.count())
                        .select_from(ScriptVersionRecord)
                        .where(
                            ScriptVersionRecord.run_id == run.id,
                            ScriptVersionRecord.origin == "auto_revision",
                        )
                    )
                    or 0
                )
                if used >= run.revision_budget:
                    raise ScriptServiceConflictError("automatic revision budget is exhausted")
                content = self._validate_content(session, run, self._template(session, run))
                version = ScriptVersionRecord(
                    run_id=run.id,
                    version_number=latest.version_number + 1,
                    parent_version_id=latest.id,
                    origin="auto_revision",
                    content=content,
                    content_sha256=self._digest(content),
                    created_by=actor,
                    command_key=key,
                )
                session.add(version)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.auto_revised",
                    actor,
                    {
                        "script_run_id": str(run.id),
                        "script_version_id": str(version.id),
                        "budget_used": used + 1,
                    },
                )
                version_id, created = version.id, True
        return self.get_version(
            project_id=project_id, run_id=run_id, version_id=version_id
        ), created

    def final_review(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        decision: str,
        reason: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        if decision not in {"approve", "reject"}:
            raise ScriptServiceConflictError("unsupported final decision")
        clean_reason = self._text(reason, "review reason", 1000)
        actor = self._text(actor_id, "reviewer", 120)
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            run = self._require_run(session, project_id, run_id)
            version = self._require_version(session, run.id, version_id)
            evaluation = session.scalar(
                select(ScriptEvaluationRecord)
                .where(ScriptEvaluationRecord.script_version_id == version.id)
                .order_by(
                    ScriptEvaluationRecord.created_at.desc(), ScriptEvaluationRecord.id.desc()
                )
            )
            if evaluation is None:
                raise ScriptServiceConflictError("evaluate this exact version before final review")
            if decision == "approve" and not evaluation.passed:
                raise ScriptServiceConflictError("a failing script cannot receive final approval")
            existing = session.scalar(
                select(ScriptFinalReviewRecord).where(
                    ScriptFinalReviewRecord.run_id == run.id,
                    ScriptFinalReviewRecord.command_key == key,
                )
            )
            expected = (version.id, evaluation.id, decision, clean_reason, actor)
            if existing is not None:
                actual = (
                    existing.script_version_id,
                    existing.evaluation_id,
                    existing.decision,
                    existing.reason,
                    existing.reviewer_id,
                )
                if actual != expected:
                    raise ScriptServiceConflictError("idempotency key belongs to another review")
                review_id, created = existing.id, False
            else:
                review = ScriptFinalReviewRecord(
                    run_id=run.id,
                    script_version_id=version.id,
                    evaluation_id=evaluation.id,
                    decision=decision,
                    reason=clean_reason,
                    reviewer_id=actor,
                    command_key=key,
                )
                session.add(review)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.final_reviewed",
                    actor,
                    {
                        "script_run_id": str(run.id),
                        "script_version_id": str(version.id),
                        "decision": decision,
                    },
                )
                review_id, created = review.id, True
        return self.get_final_review(project_id, run_id, review_id), created

    def get_final_review(
        self, project_id: UUID, run_id: UUID, review_id: UUID
    ) -> dict[str, object]:
        with self._session_factory() as session:
            self._require_run(session, project_id, run_id)
            item = session.scalar(
                select(ScriptFinalReviewRecord).where(
                    ScriptFinalReviewRecord.id == review_id,
                    ScriptFinalReviewRecord.run_id == run_id,
                )
            )
            if item is None:
                raise ScriptServiceNotFoundError("final script review not found")
            return self._final_review(item)

    def export(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        format: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        if format not in {"markdown", "json"}:
            raise ScriptServiceConflictError("export format must be markdown or json")
        key = self._key(command_key)
        with self._session_factory.begin() as session:
            self._lock_project(session, project_id)
            run = self._require_run(session, project_id, run_id)
            version = self._require_version(session, run.id, version_id)
            review = session.scalar(
                select(ScriptFinalReviewRecord)
                .where(
                    ScriptFinalReviewRecord.run_id == run.id,
                    ScriptFinalReviewRecord.script_version_id == version.id,
                    ScriptFinalReviewRecord.decision == "approve",
                )
                .order_by(
                    ScriptFinalReviewRecord.created_at.desc(), ScriptFinalReviewRecord.id.desc()
                )
            )
            if review is None:
                raise ScriptServiceConflictError("final human approval is required before export")
            content = self._render(version, format)
            digest = sha256(content.encode("utf-8")).hexdigest()
            existing = session.scalar(
                select(ScriptExportRecord).where(
                    ScriptExportRecord.run_id == run.id,
                    ScriptExportRecord.command_key == key,
                )
            )
            if existing is not None:
                if (
                    existing.script_version_id != version.id
                    or existing.final_review_id != review.id
                    or existing.format != format
                    or existing.payload_sha256 != digest
                ):
                    raise ScriptServiceConflictError("idempotency key belongs to another export")
                export_id, created = existing.id, False
            else:
                receipt = ScriptExportRecord(
                    run_id=run.id,
                    script_version_id=version.id,
                    final_review_id=review.id,
                    format=format,
                    payload_sha256=digest,
                    command_key=key,
                )
                session.add(receipt)
                session.flush()
                self._audit(
                    session,
                    project_id,
                    "script.exported",
                    "local-user",
                    {
                        "script_run_id": str(run.id),
                        "script_version_id": str(version.id),
                        "format": format,
                        "payload_sha256": digest,
                    },
                )
                export_id, created = receipt.id, True
        return {
            "id": str(export_id),
            "format": format,
            "filename": f"gamecrafter-script-v{version.version_number}.{'md' if format == 'markdown' else 'json'}",
            "media_type": "text/markdown" if format == "markdown" else "application/json",
            "content": content,
            "sha256": digest,
        }, created

    def _template(self, session: Session, run: ScriptRunRecord) -> dict[str, Any]:
        task = session.get(MarketingTaskRecord, run.marketing_task_id)
        candidate = session.get(TopicCandidateRecord, run.topic_candidate_id)
        signal = session.get(TrendSignalRecord, candidate.trend_signal_id) if candidate else None
        if task is None or candidate is None or signal is None:
            raise ScriptServiceConflictError("script input lineage is incomplete")
        members = list(
            session.scalars(
                select(KnowledgeSnapshotMemberRecord)
                .where(KnowledgeSnapshotMemberRecord.snapshot_id == run.knowledge_snapshot_id)
                .order_by(KnowledgeSnapshotMemberRecord.id)
            )
        )
        facts: list[tuple[str, str, str]] = []
        game_name = "the game"
        for member in members:
            claim = session.get(KnowledgeClaimRecord, member.claim_id)
            review = session.get(ClaimReviewRecord, member.review_id)
            if claim is None or review is None or review.approved_value is None:
                raise ScriptServiceConflictError("snapshot fact lineage is incomplete")
            value = self._plain_value(review.approved_value)
            facts.append((str(member.id), claim.predicate, value))
            if claim.predicate == "game.name":
                game_name = value
        if not facts:
            raise ScriptServiceConflictError("knowledge snapshot is empty")
        first_id, first_predicate, first_value = facts[0]
        proof_id, proof_predicate, proof_value = facts[1] if len(facts) > 1 else facts[0]
        duration = task.duration_seconds
        cuts = [round(duration * index / 5) for index in range(6)]
        return {
            "schema_version": SCHEMA_VERSION,
            "platform": "TikTok",
            "output_language": "en",
            "duration_seconds": duration,
            "title": f"{game_name}: {signal.title}",
            "caption": f"Why {game_name} belongs on your watchlist. Source-backed, creator-ready.",
            "hashtags": [self._hashtag(signal.title), "#Gaming", "#GameTok"],
            "sections": [
                {
                    "start_second": cuts[0],
                    "end_second": cuts[1],
                    "purpose": "hook",
                    "voiceover": candidate.hook,
                    "on_screen_text": signal.title,
                    "visual_direction": "Open on the strongest approved gameplay or key-art beat; label it as official footage when used.",
                    "knowledge_member_ids": [],
                    "trend_signal_ids": [str(signal.id)],
                },
                {
                    "start_second": cuts[1],
                    "end_second": cuts[2],
                    "purpose": "setup",
                    "voiceover": f"Meet {game_name}. Here is the verified reason this trend fits the game.",
                    "on_screen_text": game_name,
                    "visual_direction": "Reveal the game name and establish the premise with official material.",
                    "knowledge_member_ids": [first_id],
                    "trend_signal_ids": [str(signal.id)],
                },
                {
                    "start_second": cuts[2],
                    "end_second": cuts[3],
                    "purpose": "proof",
                    "voiceover": f"Official evidence confirms {first_predicate.replace('.', ' ')}: {first_value}.",
                    "on_screen_text": first_value,
                    "visual_direction": "Show the matching official evidence or footage; do not add unverified claims.",
                    "knowledge_member_ids": [first_id],
                    "trend_signal_ids": [],
                },
                {
                    "start_second": cuts[3],
                    "end_second": cuts[4],
                    "purpose": "payoff",
                    "voiceover": f"That makes this angle credible: {candidate.angle}. Verified detail: {proof_value}.",
                    "on_screen_text": proof_value,
                    "visual_direction": "Deliver the payoff with fast cuts grounded in the cited snapshot.",
                    "knowledge_member_ids": [proof_id],
                    "trend_signal_ids": [str(signal.id)],
                },
                {
                    "start_second": cuts[4],
                    "end_second": cuts[5],
                    "purpose": "cta",
                    "voiceover": f"Would you play {game_name}? Save this and follow for the next verified update.",
                    "on_screen_text": "Play, save, or follow?",
                    "visual_direction": "End on approved key art and a clear engagement prompt.",
                    "knowledge_member_ids": [first_id],
                    "trend_signal_ids": [],
                },
            ],
        }

    def _validate_content(
        self, session: Session, run: ScriptRunRecord, content: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(content, dict):
            raise ScriptServiceConflictError("script content must be an object")
        try:
            encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ScriptServiceConflictError("script content must be valid JSON") from error
        if len(encoded.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ScriptServiceConflictError("script content exceeds 64 KiB")
        required = {
            "schema_version",
            "platform",
            "output_language",
            "duration_seconds",
            "title",
            "caption",
            "hashtags",
            "sections",
        }
        if set(content) != required:
            raise ScriptServiceConflictError(
                "script content has missing or unknown top-level fields"
            )
        if (
            content["schema_version"] != SCHEMA_VERSION
            or content["platform"] != "TikTok"
            or content["output_language"] != "en"
        ):
            raise ScriptServiceConflictError(
                "script schema, platform, and language are fixed for v1"
            )
        task = session.get(MarketingTaskRecord, run.marketing_task_id)
        candidate = session.get(TopicCandidateRecord, run.topic_candidate_id)
        if task is None or candidate is None:
            raise ScriptServiceConflictError("script input lineage is incomplete")
        if content["duration_seconds"] != task.duration_seconds:
            raise ScriptServiceConflictError("script duration must match the marketing task")
        for name in ("title", "caption"):
            if (
                not isinstance(content[name], str)
                or not content[name].strip()
                or len(content[name]) > 1000
            ):
                raise ScriptServiceConflictError(f"script {name} is invalid")
        if (
            not isinstance(content["hashtags"], list)
            or not 1 <= len(content["hashtags"]) <= 12
            or not all(
                isinstance(item, str) and item.startswith("#") and len(item) <= 80
                for item in content["hashtags"]
            )
        ):
            raise ScriptServiceConflictError("script hashtags must contain 1 to 12 #tags")
        sections = content["sections"]
        if not isinstance(sections, list) or not 3 <= len(sections) <= 12:
            raise ScriptServiceConflictError("script must contain 3 to 12 sections")
        allowed_members = {
            str(value)
            for value in session.scalars(
                select(KnowledgeSnapshotMemberRecord.id).where(
                    KnowledgeSnapshotMemberRecord.snapshot_id == run.knowledge_snapshot_id
                )
            )
        }
        allowed_signals = {str(candidate.trend_signal_id)}
        previous = 0
        section_fields = {
            "start_second",
            "end_second",
            "purpose",
            "voiceover",
            "on_screen_text",
            "visual_direction",
            "knowledge_member_ids",
            "trend_signal_ids",
        }
        for section in sections:
            if not isinstance(section, dict) or set(section) != section_fields:
                raise ScriptServiceConflictError("each script section must use the v1 schema")
            if (
                section["start_second"] != previous
                or not isinstance(section["end_second"], int)
                or section["end_second"] <= previous
            ):
                raise ScriptServiceConflictError(
                    "script section timeline must be continuous and increasing"
                )
            previous = section["end_second"]
            for name in ("purpose", "voiceover", "on_screen_text", "visual_direction"):
                if (
                    not isinstance(section[name], str)
                    or not section[name].strip()
                    or len(section[name]) > 2000
                ):
                    raise ScriptServiceConflictError(f"section {name} is invalid")
            if not isinstance(section["knowledge_member_ids"], list) or not set(
                section["knowledge_member_ids"]
            ).issubset(allowed_members):
                raise ScriptServiceConflictError(
                    "section references knowledge outside the frozen snapshot"
                )
            if not isinstance(section["trend_signal_ids"], list) or not set(
                section["trend_signal_ids"]
            ).issubset(allowed_signals):
                raise ScriptServiceConflictError("section references an unapproved trend signal")
        if previous != task.duration_seconds:
            raise ScriptServiceConflictError("script timeline must end at task duration")
        return json.loads(encoded)

    def _score(
        self, session: Session, run: ScriptRunRecord, content: dict[str, Any]
    ) -> dict[str, Any]:
        issues: list[str] = []
        sections = content.get("sections", [])
        timeline_ok = (
            bool(sections)
            and sections[0].get("start_second") == 0
            and sections[-1].get("end_second") == content.get("duration_seconds")
        )
        hook_ok = (
            bool(sections)
            and sections[0].get("purpose") == "hook"
            and len(sections[0].get("voiceover", "").strip()) >= 12
        )
        cta_ok = any(
            item.get("purpose") == "cta"
            and any(
                word in item.get("voiceover", "").casefold()
                for word in ("follow", "save", "play", "comment")
            )
            for item in sections
        )
        evidence_ok = any(item.get("knowledge_member_ids") for item in sections) and any(
            item.get("trend_signal_ids") for item in sections
        )
        purposes = {item.get("purpose") for item in sections}
        structure_ok = {"hook", "setup", "proof", "payoff", "cta"}.issubset(purposes)
        try:
            self._validate_content(session, run, content)
            safety_ok = True
        except ScriptServiceConflictError:
            safety_ok = False
        dimensions = {
            "duration_and_timeline": {"score": 20 if timeline_ok else 0, "max": 20},
            "hook_strength": {"score": 20 if hook_ok else 0, "max": 20},
            "evidence_lineage": {"score": 20 if evidence_ok else 0, "max": 20},
            "call_to_action": {"score": 15 if cta_ok else 0, "max": 15},
            "tiktok_structure": {"score": 15 if structure_ok else 0, "max": 15},
            "schema_and_safety": {"score": 10 if safety_ok else 0, "max": 10},
        }
        labels = {
            "duration_and_timeline": timeline_ok,
            "hook_strength": hook_ok,
            "evidence_lineage": evidence_ok,
            "call_to_action": cta_ok,
            "tiktok_structure": structure_ok,
            "schema_and_safety": safety_ok,
        }
        issues.extend(f"{name}_failed" for name, passed in labels.items() if not passed)
        return {
            "score": sum(value["score"] for value in dimensions.values()),
            "dimensions": dimensions,
            "issues": issues,
        }

    def _run(self, session: Session, item: ScriptRunRecord) -> dict[str, object]:
        versions = list(
            session.scalars(
                select(ScriptVersionRecord)
                .where(ScriptVersionRecord.run_id == item.id)
                .order_by(ScriptVersionRecord.version_number)
            )
        )
        evaluations = list(
            session.scalars(
                select(ScriptEvaluationRecord)
                .where(ScriptEvaluationRecord.run_id == item.id)
                .order_by(ScriptEvaluationRecord.created_at, ScriptEvaluationRecord.id)
            )
        )
        reviews = list(
            session.scalars(
                select(ScriptFinalReviewRecord)
                .where(ScriptFinalReviewRecord.run_id == item.id)
                .order_by(ScriptFinalReviewRecord.created_at, ScriptFinalReviewRecord.id)
            )
        )
        used = sum(version.origin == "auto_revision" for version in versions)
        return {
            "id": str(item.id),
            "project_id": str(item.project_id),
            "marketing_task_id": str(item.marketing_task_id),
            "topic_candidate_id": str(item.topic_candidate_id),
            "topic_review_id": str(item.topic_review_id),
            "knowledge_snapshot_id": str(item.knowledge_snapshot_id),
            "revision_budget": item.revision_budget,
            "revisions_used": used,
            "score_threshold": item.score_threshold,
            "generator_version": item.generator_version,
            "evaluator_version": item.evaluator_version,
            "versions": [self._version(v) for v in versions],
            "evaluations": [self._evaluation(v) for v in evaluations],
            "final_reviews": [self._final_review(v) for v in reviews],
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _version(item: ScriptVersionRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "run_id": str(item.run_id),
            "version_number": item.version_number,
            "parent_version_id": str(item.parent_version_id) if item.parent_version_id else None,
            "origin": item.origin,
            "content": dict(item.content),
            "content_sha256": item.content_sha256,
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _evaluation(item: ScriptEvaluationRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "run_id": str(item.run_id),
            "script_version_id": str(item.script_version_id),
            "score": item.score,
            "passed": item.passed,
            "dimensions": dict(item.dimensions),
            "issues": list(item.issues),
            "rule_version": item.rule_version,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _final_review(item: ScriptFinalReviewRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "run_id": str(item.run_id),
            "script_version_id": str(item.script_version_id),
            "evaluation_id": str(item.evaluation_id),
            "decision": item.decision,
            "reason": item.reason,
            "reviewer_id": item.reviewer_id,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _render(version: ScriptVersionRecord, format: str) -> str:
        content = dict(version.content)
        if format == "json":
            return json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        lines = [
            f"# {content['title']}",
            "",
            content["caption"],
            "",
            f"Duration: {content['duration_seconds']}s · Platform: TikTok · Language: English",
            "",
            "## Script",
            "",
        ]
        for section in content["sections"]:
            lines.extend(
                [
                    f"### {section['start_second']}–{section['end_second']}s · {section['purpose']}",
                    f"- Voiceover: {section['voiceover']}",
                    f"- On screen: {section['on_screen_text']}",
                    f"- Visual: {section['visual_direction']}",
                    f"- Knowledge lineage: {', '.join(section['knowledge_member_ids']) or 'none'}",
                    f"- Trend lineage: {', '.join(section['trend_signal_ids']) or 'none'}",
                    "",
                ]
            )
        lines.extend(["## Caption", "", content["caption"], "", " ".join(content["hashtags"]), ""])
        return "\n".join(lines)

    @staticmethod
    def _plain_value(value: Any) -> str:
        return (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, sort_keys=True)
        )

    @staticmethod
    def _hashtag(value: str) -> str:
        cleaned = "".join(char for char in value if char.isalnum() or char == "_")
        return f"#{cleaned}" if cleaned else "#GameTrend"

    @staticmethod
    def _digest(content: dict[str, Any]) -> str:
        return sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _text(value: str, label: str, maximum: int) -> str:
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise ScriptServiceConflictError(f"{label} must contain 1 to {maximum} characters")
        return clean

    @classmethod
    def _key(cls, value: str) -> str:
        clean = cls._text(value, "idempotency key", 160)
        if len(clean) < 8:
            raise ScriptServiceConflictError("idempotency key must contain 8 to 160 characters")
        return clean

    @staticmethod
    def _audit(
        session: Session, project_id: UUID, event_type: str, actor_id: str, payload: dict[str, Any]
    ) -> None:
        session.add(
            AuditEventRecord(
                project_id=project_id,
                event_type=event_type,
                actor_type="human" if actor_id != "local-system" else "system",
                actor_id=actor_id,
                payload=payload,
            )
        )

    @staticmethod
    def _require_project(session: Session, project_id: UUID) -> ProjectRecord:
        item = session.get(ProjectRecord, project_id)
        if item is None:
            raise ScriptServiceNotFoundError("project not found")
        return item

    @classmethod
    def _lock_project(cls, session: Session, project_id: UUID) -> ProjectRecord:
        item = session.scalar(
            select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update()
        )
        if item is None:
            raise ScriptServiceNotFoundError("project not found")
        return item

    @staticmethod
    def _require_task(session: Session, project_id: UUID, task_id: UUID) -> MarketingTaskRecord:
        item = session.scalar(
            select(MarketingTaskRecord).where(
                MarketingTaskRecord.id == task_id, MarketingTaskRecord.project_id == project_id
            )
        )
        if item is None:
            raise ScriptServiceNotFoundError("marketing task not found")
        return item

    @staticmethod
    def _current_approved_review(session: Session, task_id: UUID) -> TopicReviewRecord:
        reviews = list(
            session.scalars(
                select(TopicReviewRecord)
                .where(TopicReviewRecord.task_id == task_id)
                .order_by(TopicReviewRecord.created_at, TopicReviewRecord.id)
            )
        )
        latest: dict[UUID, TopicReviewRecord] = {}
        for item in reviews:
            latest[item.candidate_id] = item
        approved = [item for item in latest.values() if item.decision == "approve"]
        if len(approved) != 1:
            raise ScriptServiceConflictError("exactly one current human-approved topic is required")
        return approved[0]

    @staticmethod
    def _require_run(session: Session, project_id: UUID, run_id: UUID) -> ScriptRunRecord:
        item = session.scalar(
            select(ScriptRunRecord).where(
                ScriptRunRecord.id == run_id, ScriptRunRecord.project_id == project_id
            )
        )
        if item is None:
            raise ScriptServiceNotFoundError("script run not found")
        return item

    @staticmethod
    def _require_version(session: Session, run_id: UUID, version_id: UUID) -> ScriptVersionRecord:
        item = session.scalar(
            select(ScriptVersionRecord).where(
                ScriptVersionRecord.id == version_id, ScriptVersionRecord.run_id == run_id
            )
        )
        if item is None:
            raise ScriptServiceNotFoundError("script version not found")
        return item

    @staticmethod
    def _latest_version(session: Session, run_id: UUID) -> ScriptVersionRecord | None:
        return session.scalar(
            select(ScriptVersionRecord)
            .where(ScriptVersionRecord.run_id == run_id)
            .order_by(ScriptVersionRecord.version_number.desc())
            .limit(1)
        )
