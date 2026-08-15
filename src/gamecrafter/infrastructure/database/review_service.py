"""Append-only human review and guarded conflict-closure commands."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.domain.knowledge.claims import (
    ClaimValueKind,
    ConflictRelation,
    ConflictStatus,
    ReviewDecision,
    normalize_claim_value,
    validate_claim_value,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    ProjectRecord,
    utc_now,
)


class ReviewServiceNotFoundError(LookupError):
    """Raised when a project, Claim, or conflict group is outside the command scope."""


class ReviewServiceConflictError(RuntimeError):
    """Raised when a human decision violates review or conflict invariants."""


class DatabaseReviewService:
    """Persist retry-safe human decisions while preserving every earlier decision."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def review_claim(
        self,
        *,
        project_id: UUID,
        claim_id: UUID,
        decision: str,
        approved_value: Any | None,
        reason: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        """Append one immutable review or replay an exact idempotent command."""

        clean_reason = self._command_metadata(
            reason=reason,
            actor_id=actor_id,
            command_key=command_key,
        )
        try:
            review_decision = ReviewDecision(decision)
        except ValueError as error:
            raise ReviewServiceConflictError("unsupported review decision") from error

        with self._session_factory.begin() as session:
            self._locked_project(session, project_id)
            claim = session.scalar(
                select(KnowledgeClaimRecord).where(
                    KnowledgeClaimRecord.id == claim_id,
                    KnowledgeClaimRecord.project_id == project_id,
                )
            )
            if claim is None:
                raise ReviewServiceNotFoundError("knowledge claim not found")
            value_kind = ClaimValueKind(claim.value_kind)
            stored_value, stored_normalized = self._review_value(
                session,
                claim=claim,
                decision=review_decision,
                approved_value=approved_value,
                value_kind=value_kind,
            )
            existing = session.scalar(
                select(ClaimReviewRecord).where(
                    ClaimReviewRecord.project_id == project_id,
                    ClaimReviewRecord.command_key == command_key,
                )
            )
            if existing is not None:
                if not self._same_review(
                    existing,
                    claim_id=claim_id,
                    decision=review_decision,
                    value_kind=value_kind,
                    approved_value=stored_value,
                    normalized_value=stored_normalized,
                    reason=clean_reason,
                    actor_id=actor_id,
                ):
                    raise ReviewServiceConflictError(
                        "idempotency key was already used for a different review command"
                    )
                return self._serialize_review(existing), False

            review = ClaimReviewRecord(
                project_id=project_id,
                claim_id=claim_id,
                decision=review_decision.value,
                approved_value_kind=(
                    value_kind.value
                    if review_decision in {ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_EDIT}
                    else None
                ),
                approved_value=stored_value,
                approved_normalized_value=stored_normalized,
                reason=clean_reason,
                reviewer_id=actor_id,
                command_key=command_key,
            )
            session.add(review)
            session.flush()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="knowledge.claim_reviewed",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "review_id": str(review.id),
                        "claim_id": str(claim_id),
                        "decision": review_decision.value,
                        "edited": review_decision is ReviewDecision.APPROVE_WITH_EDIT,
                    },
                )
            )
            return self._serialize_review(review), True

    def list_reviews(
        self,
        project_id: UUID,
        *,
        claim_id: UUID | None = None,
        subject_entity_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Return append-only review history in causal order."""

        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise ReviewServiceNotFoundError("project not found")
            statement = (
                select(ClaimReviewRecord)
                .join(KnowledgeClaimRecord, KnowledgeClaimRecord.id == ClaimReviewRecord.claim_id)
                .where(ClaimReviewRecord.project_id == project_id)
            )
            if claim_id is not None:
                statement = statement.where(ClaimReviewRecord.claim_id == claim_id)
            if subject_entity_id is not None:
                statement = statement.where(
                    KnowledgeClaimRecord.subject_entity_id == subject_entity_id
                )
            reviews = session.scalars(
                statement.order_by(ClaimReviewRecord.created_at, ClaimReviewRecord.id)
            )
            return [self._serialize_review(review) for review in reviews]

    def close_conflict(
        self,
        *,
        project_id: UUID,
        conflict_group_id: UUID,
        outcome: str,
        reason: str,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        """Resolve a fully reviewed group or explicitly dismiss it as non-actionable."""

        clean_reason = self._command_metadata(
            reason=reason,
            actor_id=actor_id,
            command_key=command_key,
        )
        try:
            status = ConflictStatus(outcome)
        except ValueError as error:
            raise ReviewServiceConflictError("unsupported conflict closure outcome") from error
        if status is ConflictStatus.OPEN:
            raise ReviewServiceConflictError("conflict closure outcome cannot be open")

        with self._session_factory.begin() as session:
            self._locked_project(session, project_id)
            reused = session.scalar(
                select(ClaimConflictGroupRecord).where(
                    ClaimConflictGroupRecord.project_id == project_id,
                    ClaimConflictGroupRecord.resolution_command_key == command_key,
                )
            )
            if reused is not None:
                if (
                    reused.id != conflict_group_id
                    or reused.status != status.value
                    or reused.resolution_summary != clean_reason
                    or reused.resolved_by != actor_id
                ):
                    raise ReviewServiceConflictError(
                        "idempotency key was already used for a different conflict closure"
                    )
                return self._serialize_closure(reused), False

            group = session.scalar(
                select(ClaimConflictGroupRecord)
                .where(
                    ClaimConflictGroupRecord.id == conflict_group_id,
                    ClaimConflictGroupRecord.project_id == project_id,
                )
                .with_for_update()
            )
            if group is None:
                raise ReviewServiceNotFoundError("knowledge conflict group not found")
            if group.status != ConflictStatus.OPEN.value:
                raise ReviewServiceConflictError("knowledge conflict group is already closed")

            review_counts: Counter[str] = Counter()
            if status is ConflictStatus.RESOLVED:
                review_counts = self._validate_resolution(session, group)
            group.status = status.value
            group.resolution_summary = clean_reason
            group.resolved_by = actor_id
            group.resolved_at = utc_now()
            group.resolution_command_key = command_key
            group.resolution_review_counts = dict(review_counts)
            session.flush()
            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type=f"knowledge.conflict_{status.value}",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "conflict_group_id": str(group.id),
                        "outcome": status.value,
                        "review_counts": dict(review_counts),
                    },
                )
            )
            return self._serialize_closure(group), True

    @staticmethod
    def _review_value(
        session: Session,
        *,
        claim: KnowledgeClaimRecord,
        decision: ReviewDecision,
        approved_value: Any | None,
        value_kind: ClaimValueKind,
    ) -> tuple[Any | None, str | None]:
        if decision in {ReviewDecision.REJECT, ReviewDecision.DEFER}:
            if approved_value is not None:
                raise ReviewServiceConflictError(
                    "reject and defer decisions cannot include an approved value"
                )
            return None, None
        if (
            session.scalar(
                select(ClaimEvidenceSpanRecord.id)
                .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
                .limit(1)
            )
            is None
        ):
            raise ReviewServiceConflictError("a claim without exact evidence cannot be approved")
        if decision is ReviewDecision.APPROVE:
            if approved_value is not None:
                raise ReviewServiceConflictError(
                    "approve copies the immutable candidate value; use approve_with_edit to edit"
                )
            return claim.value, claim.normalized_value
        if approved_value is None:
            raise ReviewServiceConflictError("approve_with_edit requires an approved value")
        try:
            encoded = json.dumps(
                approved_value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if len(encoded) > 16_384:
                raise ReviewServiceConflictError("approved value exceeds 16384 UTF-8 bytes")
            validate_claim_value(value_kind, approved_value)
            normalized = normalize_claim_value(value_kind, approved_value)
        except (TypeError, ValueError) as error:
            raise ReviewServiceConflictError(str(error)) from error
        if normalized == claim.normalized_value:
            raise ReviewServiceConflictError(
                "edited value is equivalent to the candidate; use approve instead"
            )
        return approved_value, normalized

    @staticmethod
    def _same_review(
        review: ClaimReviewRecord,
        *,
        claim_id: UUID,
        decision: ReviewDecision,
        value_kind: ClaimValueKind,
        approved_value: Any | None,
        normalized_value: str | None,
        reason: str,
        actor_id: str,
    ) -> bool:
        expected_kind = (
            value_kind.value
            if decision in {ReviewDecision.APPROVE, ReviewDecision.APPROVE_WITH_EDIT}
            else None
        )
        return (
            review.claim_id == claim_id
            and review.decision == decision.value
            and review.approved_value_kind == expected_kind
            and review.approved_value == approved_value
            and review.approved_normalized_value == normalized_value
            and review.reason == reason
            and review.reviewer_id == actor_id
        )

    @staticmethod
    def _validate_resolution(
        session: Session,
        group: ClaimConflictGroupRecord,
    ) -> Counter[str]:
        members = list(
            session.scalars(
                select(ClaimConflictMemberRecord).where(
                    ClaimConflictMemberRecord.conflict_group_id == group.id
                )
            )
        )
        if not members:
            raise ReviewServiceConflictError("an empty conflict group cannot be resolved")
        relations = {member.relation for member in members}
        if len(relations) != 1:
            raise ReviewServiceConflictError("conflict group has inconsistent member relations")

        latest: list[tuple[KnowledgeClaimRecord, ClaimReviewRecord]] = []
        counts: Counter[str] = Counter()
        for member in members:
            claim = session.get(KnowledgeClaimRecord, member.claim_id)
            if claim is None:
                raise ReviewServiceConflictError("conflict member Claim is missing")
            review = session.scalar(
                select(ClaimReviewRecord)
                .where(ClaimReviewRecord.claim_id == claim.id)
                .order_by(ClaimReviewRecord.created_at.desc(), ClaimReviewRecord.id.desc())
                .limit(1)
            )
            if review is None or review.decision == ReviewDecision.DEFER.value:
                raise ReviewServiceConflictError(
                    "every conflict member needs a final approve or reject review"
                )
            counts[review.decision] += 1
            latest.append((claim, review))

        approvals = [
            review
            for _, review in latest
            if review.decision
            in {
                ReviewDecision.APPROVE.value,
                ReviewDecision.APPROVE_WITH_EDIT.value,
            }
        ]
        if not approvals:
            raise ReviewServiceConflictError(
                "resolved conflict must retain at least one approved value"
            )
        if relations == {ConflictRelation.CONFLICTING.value}:
            approved_values = {review.approved_normalized_value for review in approvals}
            if len(approved_values) != 1:
                raise ReviewServiceConflictError(
                    "a conflicting single-valued group must retain exactly one approved value"
                )
        return counts

    @staticmethod
    def _command_metadata(*, reason: str, actor_id: str, command_key: str) -> str:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ReviewServiceConflictError("human decision reason must not be blank")
        if len(clean_reason) > 1000:
            raise ReviewServiceConflictError("human decision reason exceeds 1000 characters")
        if not actor_id.strip() or len(actor_id) > 120:
            raise ReviewServiceConflictError("human actor identity is invalid")
        if not 8 <= len(command_key) <= 160 or not command_key.strip():
            raise ReviewServiceConflictError("idempotency key must contain 8 to 160 characters")
        return clean_reason

    @staticmethod
    def _locked_project(session: Session, project_id: UUID) -> ProjectRecord:
        project = session.scalar(
            select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update()
        )
        if project is None:
            raise ReviewServiceNotFoundError("project not found")
        return project

    @staticmethod
    def _serialize_review(review: ClaimReviewRecord) -> dict[str, object]:
        return {
            "id": str(review.id),
            "project_id": str(review.project_id),
            "claim_id": str(review.claim_id),
            "decision": review.decision,
            "approved_value_kind": review.approved_value_kind,
            "approved_value": review.approved_value,
            "approved_normalized_value": review.approved_normalized_value,
            "reason": review.reason,
            "reviewer_id": review.reviewer_id,
            "created_at": review.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_closure(
        group: ClaimConflictGroupRecord,
    ) -> dict[str, object]:
        return {
            "id": str(group.id),
            "project_id": str(group.project_id),
            "status": group.status,
            "resolution_summary": group.resolution_summary,
            "resolved_by": group.resolved_by,
            "resolved_at": group.resolved_at.isoformat() if group.resolved_at else None,
            "review_counts": group.resolution_review_counts or {},
        }
