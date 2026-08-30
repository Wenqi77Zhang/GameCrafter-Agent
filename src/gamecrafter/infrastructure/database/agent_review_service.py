"""Durable independent agent review and one-command human confirmation."""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.agent_catalog import KNOWLEDGE_REVIEWER
from gamecrafter.application.ports.agent_review_repository import AgentReviewStateError
from gamecrafter.application.ports.review_gateway import (
    REVIEW_PROMPT_VERSION,
    REVIEW_SCHEMA_VERSION,
    AgentClaimDecision,
    ReviewCandidate,
)
from gamecrafter.domain.knowledge.claims import ReviewDecision
from gamecrafter.infrastructure.database.models import (
    AgentReviewResultRecord,
    AuditEventRecord,
    ClaimAgentReviewRecord,
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRecord,
    KnowledgeExtractionResultRecord,
    WorkflowRunRecord,
)


class AgentReviewNotFoundError(AgentReviewStateError, LookupError):
    pass


class AgentReviewConflictError(AgentReviewStateError):
    pass


def _identity_is_direct_subject(value: str, quote: str) -> bool:
    """Conservatively recognize a character name used as the quoted clause subject."""

    name = value.strip().casefold()
    evidence = quote.strip().casefold()
    if not name or not evidence.startswith(name):
        return False
    suffix = evidence[len(name) :]
    return not suffix.startswith(("'s", "’s"))


class DatabaseAgentReviewService:
    """Keeps model review immutable, bounded, idempotent, and human-controlled."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def project_id_for_run(self, run_id: UUID) -> UUID:
        with self._session_factory() as session:
            run = session.get(WorkflowRunRecord, run_id)
            if run is None:
                raise AgentReviewNotFoundError("review workflow run not found")
            return run.project_id

    def completed_run(self, *, project_id: UUID, extraction_run_id: UUID) -> UUID | None:
        with self._session_factory() as session:
            return session.scalar(
                select(AgentReviewResultRecord.run_id)
                .join(WorkflowRunRecord, WorkflowRunRecord.id == AgentReviewResultRecord.run_id)
                .where(
                    AgentReviewResultRecord.project_id == project_id,
                    AgentReviewResultRecord.extraction_run_id == extraction_run_id,
                    AgentReviewResultRecord.reviewer_version == KNOWLEDGE_REVIEWER.version,
                    WorkflowRunRecord.status == "succeeded",
                )
                .limit(1)
            )

    def candidates(
        self, *, project_id: UUID, extraction_run_id: UUID
    ) -> tuple[str, tuple[ReviewCandidate, ...]]:
        with self._session_factory() as session:
            extraction = session.get(KnowledgeExtractionResultRecord, extraction_run_id)
            if extraction is None or extraction.project_id != project_id:
                raise AgentReviewNotFoundError("successful knowledge extraction not found")
            entity = session.get(KnowledgeEntityRecord, extraction.subject_entity_id)
            if entity is None or entity.project_id != project_id:
                raise AgentReviewNotFoundError("knowledge entity not found")
            claims = list(
                session.scalars(
                    select(KnowledgeClaimRecord)
                    .where(
                        KnowledgeClaimRecord.project_id == project_id,
                        KnowledgeClaimRecord.extraction_run_id == extraction_run_id,
                    )
                    .order_by(KnowledgeClaimRecord.created_at, KnowledgeClaimRecord.id)
                )
            )
            if not claims:
                raise AgentReviewConflictError("extraction has no candidate claims")
            candidates: list[ReviewCandidate] = []
            for claim in claims:
                quotes = tuple(
                    span.quote
                    for span in session.scalars(
                        select(ClaimEvidenceSpanRecord)
                        .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
                        .order_by(ClaimEvidenceSpanRecord.ordinal)
                    )
                )
                if not quotes:
                    raise AgentReviewConflictError("claim has no exact evidence quote")
                candidates.append(
                    ReviewCandidate(
                        claim_id=claim.id,
                        predicate=claim.predicate,
                        value_kind=claim.value_kind,
                        value=claim.value,
                        evidence_quotes=quotes,
                    )
                )
            return entity.canonical_key, tuple(candidates)

    def persist(
        self,
        *,
        run_id: UUID,
        project_id: UUID,
        extraction_run_id: UUID,
        provider: str,
        model: str,
        fingerprints: tuple[str, ...],
        decisions: tuple[AgentClaimDecision, ...],
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> dict[str, object]:
        with self._session_factory.begin() as session:
            existing = session.get(AgentReviewResultRecord, run_id)
            if existing is not None:
                return self._summary(session, existing)
            run = session.get(WorkflowRunRecord, run_id, with_for_update=True)
            if run is None or run.project_id != project_id:
                raise AgentReviewNotFoundError("review workflow run not found")
            claims = list(
                session.scalars(
                    select(KnowledgeClaimRecord).where(
                        KnowledgeClaimRecord.project_id == project_id,
                        KnowledgeClaimRecord.extraction_run_id == extraction_run_id,
                    )
                )
            )
            by_id = {claim.id: claim for claim in claims}
            if {item.claim_id for item in decisions} != set(by_id):
                raise AgentReviewConflictError("review decisions do not cover the extraction")

            # Deterministic governance is applied after the model: exact duplicates lose,
            # then only the 15 highest-priority approvals remain in the proposed pack.
            governed = list(decisions)
            inference_markers = (
                "infer",
                "typically",
                "standard duration",
                "not explicitly",
                "assum",
            )
            governed = [
                AgentClaimDecision(
                    item.claim_id,
                    "agent_rejected",
                    item.suggested_predicate,
                    0,
                    "unsupported_inference",
                    "Rejected because the review relies on unstated context.",
                    tuple(sorted(set((*item.risk_codes, "unsupported_inference")))),
                )
                if item.decision == "agent_approved"
                and any(marker in f" {item.rationale.casefold()}" for marker in inference_markers)
                else item
                for item in governed
            ]
            ambiguous_identities: set[UUID] = set()
            for claim in claims:
                if claim.predicate != "character.identity" or not isinstance(claim.value, str):
                    continue
                quotes = tuple(
                    session.scalars(
                        select(ClaimEvidenceSpanRecord.quote)
                        .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
                        .order_by(ClaimEvidenceSpanRecord.ordinal)
                    )
                )
                if quotes and not any(
                    _identity_is_direct_subject(claim.value, quote) for quote in quotes
                ):
                    ambiguous_identities.add(claim.id)
            governed = [
                AgentClaimDecision(
                    item.claim_id,
                    "needs_human",
                    item.suggested_predicate,
                    item.priority,
                    "identity_context_ambiguous",
                    "The name is mentioned, but the quote does not clearly "
                    "describe that character.",
                    tuple(sorted(set((*item.risk_codes, "semantic_scope")))),
                )
                if item.decision == "agent_approved" and item.claim_id in ambiguous_identities
                else item
                for item in governed
            ]
            governed = [
                AgentClaimDecision(
                    item.claim_id,
                    "needs_human",
                    item.suggested_predicate,
                    item.priority,
                    "reviewer_risk",
                    item.rationale,
                    item.risk_codes,
                )
                if item.decision == "agent_approved" and item.risk_codes
                else item
                for item in governed
            ]
            governed = [
                AgentClaimDecision(
                    item.claim_id,
                    "needs_human",
                    item.suggested_predicate,
                    item.priority,
                    "predicate_correction",
                    item.rationale,
                    tuple(sorted(set((*item.risk_codes, "taxonomy")))),
                )
                if item.decision == "agent_approved" and item.suggested_predicate is not None
                else item
                for item in governed
            ]
            seen: set[tuple[str, str]] = set()
            for index, item in enumerate(governed):
                claim = by_id[item.claim_id]
                key = (claim.predicate, claim.normalized_value)
                if key in seen:
                    governed[index] = AgentClaimDecision(
                        item.claim_id,
                        "agent_rejected",
                        item.suggested_predicate,
                        0,
                        "exact_duplicate",
                        "An identical fact already exists in this extraction.",
                        tuple(sorted(set((*item.risk_codes, "duplicate")))),
                    )
                else:
                    seen.add(key)
            approved = sorted(
                (item for item in governed if item.decision == "agent_approved"),
                key=lambda item: (-item.priority, str(item.claim_id)),
            )
            excess = {item.claim_id for item in approved[15:]}
            governed = [
                AgentClaimDecision(
                    item.claim_id,
                    "agent_rejected",
                    item.suggested_predicate,
                    item.priority,
                    "low_priority",
                    "Excluded by the bounded 15-fact knowledge-pack policy.",
                    tuple(sorted(set((*item.risk_codes, "pack_limit")))),
                )
                if item.claim_id in excess
                else item
                for item in governed
            ]
            counts = {key: 0 for key in ("agent_approved", "agent_rejected", "needs_human")}
            for item in governed:
                counts[item.decision] += 1
            fingerprint = sha256("\0".join(fingerprints).encode()).hexdigest()
            result = AgentReviewResultRecord(
                run_id=run_id,
                project_id=project_id,
                extraction_run_id=extraction_run_id,
                reviewer_agent_key=KNOWLEDGE_REVIEWER.key,
                reviewer_version=KNOWLEDGE_REVIEWER.version,
                provider=provider,
                model=model,
                prompt_version=REVIEW_PROMPT_VERSION,
                schema_version=REVIEW_SCHEMA_VERSION,
                input_fingerprint_sha256=fingerprint,
                reviewed_count=len(governed),
                approved_count=counts["agent_approved"],
                rejected_count=counts["agent_rejected"],
                needs_human_count=counts["needs_human"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
            session.add(result)
            session.flush()
            for item in governed:
                session.add(
                    ClaimAgentReviewRecord(
                        project_id=project_id,
                        reviewer_run_id=run_id,
                        claim_id=item.claim_id,
                        decision=item.decision,
                        suggested_predicate=item.suggested_predicate,
                        priority=item.priority,
                        reason_code=item.reason_code,
                        rationale=item.rationale,
                        risk_codes=list(item.risk_codes),
                    )
                )
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=run_id,
                    event_type="knowledge.agent_reviewed",
                    actor_type="model",
                    actor_id=KNOWLEDGE_REVIEWER.key,
                    payload={
                        "agent_version": KNOWLEDGE_REVIEWER.version,
                        "extraction_run_id": str(extraction_run_id),
                        "counts": counts,
                        "provider": provider,
                        "model": model,
                        "input_fingerprint_sha256": fingerprint,
                    },
                )
            )
            return self._summary(session, result)

    def get_summary(self, *, project_id: UUID, extraction_run_id: UUID) -> dict[str, object]:
        with self._session_factory() as session:
            result = session.scalar(
                select(AgentReviewResultRecord)
                .where(
                    AgentReviewResultRecord.project_id == project_id,
                    AgentReviewResultRecord.extraction_run_id == extraction_run_id,
                )
                .order_by(AgentReviewResultRecord.created_at.desc())
                .limit(1)
            )
            if result is None:
                raise AgentReviewNotFoundError("agent review not found")
            return self._summary(session, result)

    def confirm_pack(
        self, *, project_id: UUID, extraction_run_id: UUID, command_key: str, actor_id: str
    ) -> dict[str, object]:
        if not 8 <= len(command_key) <= 160:
            raise AgentReviewConflictError("idempotency key must contain 8 to 160 characters")
        with self._session_factory.begin() as session:
            result = session.scalar(
                select(AgentReviewResultRecord)
                .where(
                    AgentReviewResultRecord.project_id == project_id,
                    AgentReviewResultRecord.extraction_run_id == extraction_run_id,
                )
                .order_by(AgentReviewResultRecord.created_at.desc())
                .limit(1)
            )
            if result is None:
                raise AgentReviewNotFoundError("agent review not found")
            decisions = list(
                session.scalars(
                    select(ClaimAgentReviewRecord).where(
                        ClaimAgentReviewRecord.reviewer_run_id == result.run_id
                    )
                )
            )
            created = 0
            for decision in decisions:
                if decision.decision == "needs_human":
                    continue
                derived_key = (
                    "agent-pack:"
                    + sha256(f"{command_key}\0{decision.claim_id}".encode()).hexdigest()[:48]
                )
                existing = session.scalar(
                    select(ClaimReviewRecord).where(
                        ClaimReviewRecord.project_id == project_id,
                        ClaimReviewRecord.command_key == derived_key,
                    )
                )
                if existing is not None:
                    continue
                claim = session.get(KnowledgeClaimRecord, decision.claim_id)
                if claim is None:
                    raise AgentReviewNotFoundError("knowledge claim not found")
                approve = decision.decision == "agent_approved"
                expected = ReviewDecision.APPROVE.value if approve else ReviewDecision.REJECT.value
                latest = session.scalar(
                    select(ClaimReviewRecord)
                    .where(ClaimReviewRecord.claim_id == claim.id)
                    .order_by(ClaimReviewRecord.created_at.desc(), ClaimReviewRecord.id.desc())
                    .limit(1)
                )
                if latest is not None and latest.decision == expected:
                    continue
                session.add(
                    ClaimReviewRecord(
                        project_id=project_id,
                        claim_id=claim.id,
                        decision=expected,
                        approved_value_kind=(claim.value_kind if approve else None),
                        approved_value=(claim.value if approve else None),
                        approved_normalized_value=(claim.normalized_value if approve else None),
                        reason=f"批量确认 Knowledge Reviewer 建议：{decision.reason_code}",
                        reviewer_id=actor_id,
                        command_key=derived_key,
                    )
                )
                created += 1
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    run_id=result.run_id,
                    event_type="knowledge.agent_pack_confirmed",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "extraction_run_id": str(extraction_run_id),
                        "created_review_count": created,
                        "needs_human_count": result.needs_human_count,
                    },
                )
            )
            return {"created_review_count": created, "needs_human_count": result.needs_human_count}

    @staticmethod
    def _summary(session: Session, result: AgentReviewResultRecord) -> dict[str, object]:
        decisions = list(
            session.scalars(
                select(ClaimAgentReviewRecord)
                .where(ClaimAgentReviewRecord.reviewer_run_id == result.run_id)
                .order_by(ClaimAgentReviewRecord.priority.desc(), ClaimAgentReviewRecord.id)
            )
        )
        return {
            "run_id": str(result.run_id),
            "extraction_run_id": str(result.extraction_run_id),
            "agent": {
                "key": result.reviewer_agent_key,
                "version": result.reviewer_version,
                "provider": result.provider,
                "model": result.model,
            },
            "counts": {
                "reviewed": result.reviewed_count,
                "agent_approved": result.approved_count,
                "agent_rejected": result.rejected_count,
                "needs_human": result.needs_human_count,
            },
            "token_usage": {
                "input": result.input_tokens,
                "output": result.output_tokens,
                "total": result.total_tokens,
            },
            "decisions": [
                {
                    "claim_id": str(item.claim_id),
                    "decision": item.decision,
                    "suggested_predicate": item.suggested_predicate,
                    "priority": item.priority,
                    "reason_code": item.reason_code,
                    "rationale": item.rationale,
                    "risk_codes": item.risk_codes,
                }
                for item in decisions
            ],
            "created_at": result.created_at.isoformat(),
        }
