"""Atomic, immutable publication of the complete currently approved knowledge state."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.domain.knowledge.claims import FactPredicate, ReviewDecision
from gamecrafter.domain.knowledge.conflicts import classify_predicate
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimConflictGroupRecord,
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeEntityRecord,
    KnowledgeEntityRevisionRecord,
    KnowledgeSnapshotMemberRecord,
    KnowledgeSnapshotRecord,
    ProjectRecord,
    SourceRecord,
    SourceVersionRecord,
)

SNAPSHOT_SCHEMA_VERSION = "knowledge-snapshot-v1"


class SnapshotServiceNotFoundError(LookupError):
    """Raised when the publication project or requested snapshot does not exist."""


class SnapshotServiceConflictError(RuntimeError):
    """Raised when the current review state is unsafe to publish."""


@dataclass(slots=True)
class _PublicationPlan:
    claims: list[KnowledgeClaimRecord]
    approvals: list[tuple[KnowledgeClaimRecord, ClaimReviewRecord, KnowledgeEntityRevisionRecord]]
    blockers: list[dict[str, object]]
    stats: dict[str, int]
    members: list[dict[str, object]]
    content_sha256: str | None


class DatabaseSnapshotService:
    """Publish all latest approved values only after project-wide safety gates pass."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def readiness(self, project_id: UUID) -> dict[str, object]:
        """Explain every current publication blocker without mutating state."""

        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise SnapshotServiceNotFoundError("project not found")
            plan = self._plan(session, project_id)
            latest = session.scalar(
                select(KnowledgeSnapshotRecord)
                .where(KnowledgeSnapshotRecord.project_id == project_id)
                .order_by(KnowledgeSnapshotRecord.version_number.desc())
                .limit(1)
            )
            return {
                "publishable": not plan.blockers,
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "content_sha256": plan.content_sha256,
                "stats": plan.stats,
                "blockers": plan.blockers,
                "next_version_number": (latest.version_number + 1) if latest else 1,
                "latest_snapshot_id": str(latest.id) if latest else None,
            }

    def publish(
        self,
        *,
        project_id: UUID,
        notes: str | None,
        actor_id: str,
        command_key: str,
    ) -> tuple[dict[str, object], bool]:
        """Atomically freeze the complete latest approved state as a new version."""

        clean_notes = notes.strip() if notes is not None else None
        if clean_notes == "":
            clean_notes = None
        if clean_notes is not None and len(clean_notes) > 2000:
            raise SnapshotServiceConflictError("snapshot notes exceed 2000 characters")
        if not actor_id.strip() or len(actor_id) > 120:
            raise SnapshotServiceConflictError("publisher identity is invalid")
        if not 8 <= len(command_key) <= 160 or not command_key.strip():
            raise SnapshotServiceConflictError("idempotency key must contain 8 to 160 characters")

        snapshot_id: UUID
        created = False
        with self._session_factory.begin() as session:
            project = session.scalar(
                select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update()
            )
            if project is None:
                raise SnapshotServiceNotFoundError("project not found")
            existing = session.scalar(
                select(KnowledgeSnapshotRecord).where(
                    KnowledgeSnapshotRecord.project_id == project_id,
                    KnowledgeSnapshotRecord.command_key == command_key,
                )
            )
            if existing is not None:
                if existing.notes != clean_notes or existing.published_by != actor_id:
                    raise SnapshotServiceConflictError(
                        "idempotency key was already used for a different snapshot command"
                    )
                snapshot_id = existing.id
            else:
                plan = self._plan(session, project_id)
                if plan.blockers:
                    codes = ", ".join(str(item["code"]) for item in plan.blockers)
                    raise SnapshotServiceConflictError(f"knowledge publication blocked: {codes}")
                if plan.content_sha256 is None:
                    raise SnapshotServiceConflictError("knowledge publication has no content")
                version_number = (
                    session.scalar(
                        select(func.max(KnowledgeSnapshotRecord.version_number)).where(
                            KnowledgeSnapshotRecord.project_id == project_id
                        )
                    )
                    or 0
                ) + 1
                snapshot = KnowledgeSnapshotRecord(
                    project_id=project_id,
                    version_number=version_number,
                    content_sha256=plan.content_sha256,
                    schema_version=SNAPSHOT_SCHEMA_VERSION,
                    command_key=command_key,
                    published_by=actor_id,
                    notes=clean_notes,
                )
                session.add(snapshot)
                session.flush()
                for claim, review, entity_revision in plan.approvals:
                    session.add(
                        KnowledgeSnapshotMemberRecord(
                            snapshot_id=snapshot.id,
                            claim_id=claim.id,
                            review_id=review.id,
                            entity_revision_id=entity_revision.id,
                        )
                    )
                session.flush()
                session.add(
                    AuditEventRecord(
                        project_id=project_id,
                        event_type="knowledge.snapshot_published",
                        actor_type="human",
                        actor_id=actor_id,
                        payload={
                            "snapshot_id": str(snapshot.id),
                            "version_number": version_number,
                            "schema_version": SNAPSHOT_SCHEMA_VERSION,
                            "content_sha256": plan.content_sha256,
                            "member_count": len(plan.approvals),
                        },
                    )
                )
                snapshot_id = snapshot.id
                created = True
        return self.get_snapshot(project_id=project_id, snapshot_id=snapshot_id), created

    def list_snapshots(self, project_id: UUID) -> list[dict[str, object]]:
        """Return immutable versions newest first with their exact review lineage."""

        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise SnapshotServiceNotFoundError("project not found")
            snapshots = list(
                session.scalars(
                    select(KnowledgeSnapshotRecord)
                    .where(KnowledgeSnapshotRecord.project_id == project_id)
                    .order_by(KnowledgeSnapshotRecord.version_number.desc())
                )
            )
            return [
                self._serialize_snapshot(session, snapshot, is_latest=index == 0)
                for index, snapshot in enumerate(snapshots)
            ]

    def get_snapshot(
        self,
        *,
        project_id: UUID,
        snapshot_id: UUID,
    ) -> dict[str, object]:
        with self._session_factory() as session:
            snapshot = session.scalar(
                select(KnowledgeSnapshotRecord).where(
                    KnowledgeSnapshotRecord.id == snapshot_id,
                    KnowledgeSnapshotRecord.project_id == project_id,
                )
            )
            if snapshot is None:
                raise SnapshotServiceNotFoundError("knowledge snapshot not found")
            latest_version = session.scalar(
                select(func.max(KnowledgeSnapshotRecord.version_number)).where(
                    KnowledgeSnapshotRecord.project_id == project_id
                )
            )
            return self._serialize_snapshot(
                session,
                snapshot,
                is_latest=snapshot.version_number == latest_version,
            )

    def _plan(self, session: Session, project_id: UUID) -> _PublicationPlan:
        claims = list(
            session.scalars(
                select(KnowledgeClaimRecord)
                .where(KnowledgeClaimRecord.project_id == project_id)
                .order_by(KnowledgeClaimRecord.created_at, KnowledgeClaimRecord.id)
            )
        )
        reviews = list(
            session.scalars(
                select(ClaimReviewRecord)
                .where(ClaimReviewRecord.project_id == project_id)
                .order_by(ClaimReviewRecord.created_at, ClaimReviewRecord.id)
            )
        )
        latest: dict[UUID, ClaimReviewRecord] = {}
        for review in reviews:
            latest[review.claim_id] = review

        stats = {
            "claim_count": len(claims),
            "approved_count": 0,
            "rejected_count": 0,
            "deferred_count": 0,
            "unreviewed_count": 0,
            "open_conflict_count": 0,
        }
        blockers: list[dict[str, object]] = []
        if not claims:
            blockers.append(self._blocker("no_claims", "No candidate Claims exist."))

        reviewed_approvals: list[tuple[KnowledgeClaimRecord, ClaimReviewRecord]] = []
        for claim in claims:
            review = latest.get(claim.id)
            if review is None:
                stats["unreviewed_count"] += 1
                continue
            if review.decision == ReviewDecision.DEFER.value:
                stats["deferred_count"] += 1
            elif review.decision == ReviewDecision.REJECT.value:
                stats["rejected_count"] += 1
            else:
                stats["approved_count"] += 1
                reviewed_approvals.append((claim, review))

        if stats["unreviewed_count"]:
            blockers.append(
                self._blocker(
                    "unreviewed_claims",
                    "Every Claim needs a final human decision before publication.",
                    count=stats["unreviewed_count"],
                )
            )
        if stats["deferred_count"]:
            blockers.append(
                self._blocker(
                    "deferred_claims",
                    "Deferred Claims are not final human decisions.",
                    count=stats["deferred_count"],
                )
            )
        if claims and not reviewed_approvals:
            blockers.append(
                self._blocker(
                    "no_approved_claims",
                    "At least one current human review must approve a value.",
                )
            )

        open_groups = list(
            session.scalars(
                select(ClaimConflictGroupRecord).where(
                    ClaimConflictGroupRecord.project_id == project_id,
                    ClaimConflictGroupRecord.status == "open",
                )
            )
        )
        stats["open_conflict_count"] = len(open_groups)
        if open_groups:
            blockers.append(
                self._blocker(
                    "open_conflicts",
                    "Every open conflict group must be resolved or dismissed.",
                    count=len(open_groups),
                )
            )

        approvals = self._freeze_entity_revisions(session, reviewed_approvals, blockers)
        self._append_conflict_blockers(session, project_id, claims, latest, blockers)
        members: list[dict[str, object]] = []
        for claim, review, entity_revision in approvals:
            try:
                members.append(self._member_payload(session, claim, review, entity_revision))
            except SnapshotServiceConflictError as error:
                blockers.append(
                    self._blocker(
                        "incomplete_lineage",
                        str(error),
                        claim_id=str(claim.id),
                    )
                )
        members.sort(key=lambda item: str(item["sort_key"]))
        canonical_members = [
            {key: value for key, value in item.items() if key != "sort_key"} for item in members
        ]
        content_sha256 = None
        if canonical_members and not blockers:
            content_sha256 = sha256(
                self._canonical_json(
                    {
                        "schema_version": SNAPSHOT_SCHEMA_VERSION,
                        "members": canonical_members,
                    }
                ).encode("utf-8")
            ).hexdigest()
        return _PublicationPlan(
            claims=claims,
            approvals=approvals,
            blockers=blockers,
            stats=stats,
            members=canonical_members,
            content_sha256=content_sha256,
        )

    @staticmethod
    def _freeze_entity_revisions(
        session: Session,
        approvals: list[tuple[KnowledgeClaimRecord, ClaimReviewRecord]],
        blockers: list[dict[str, object]],
    ) -> list[tuple[KnowledgeClaimRecord, ClaimReviewRecord, KnowledgeEntityRevisionRecord]]:
        archived_ids: set[UUID] = set()
        frozen: list[
            tuple[KnowledgeClaimRecord, ClaimReviewRecord, KnowledgeEntityRevisionRecord]
        ] = []
        for claim, review in approvals:
            revision = session.scalar(
                select(KnowledgeEntityRevisionRecord)
                .where(KnowledgeEntityRevisionRecord.entity_id == claim.subject_entity_id)
                .order_by(KnowledgeEntityRevisionRecord.revision_number.desc())
                .limit(1)
            )
            if revision is None:
                blockers.append(
                    DatabaseSnapshotService._blocker(
                        "incomplete_entity_lineage",
                        "Approved knowledge has no immutable entity revision.",
                        claim_id=str(claim.id),
                    )
                )
                continue
            frozen.append((claim, review, revision))
            if revision.status == "archived":
                archived_ids.add(claim.subject_entity_id)
        if archived_ids:
            blockers.append(
                DatabaseSnapshotService._blocker(
                    "approved_archived_entities",
                    "Approved values attached to archived entities cannot be published.",
                    count=len(archived_ids),
                )
            )
        return frozen

    @staticmethod
    def _append_conflict_blockers(
        session: Session,
        project_id: UUID,
        claims: list[KnowledgeClaimRecord],
        latest: dict[UUID, ClaimReviewRecord],
        blockers: list[dict[str, object]],
    ) -> None:
        grouped: dict[tuple[UUID, str, str], list[KnowledgeClaimRecord]] = defaultdict(list)
        for claim in claims:
            grouped[
                (claim.subject_entity_id, claim.predicate, claim.scope_fingerprint_sha256)
            ].append(claim)
        for (subject_id, predicate, scope), scoped_claims in grouped.items():
            approved_values = {
                review.approved_normalized_value
                for claim in scoped_claims
                if (review := latest.get(claim.id)) is not None
                and review.decision
                in {ReviewDecision.APPROVE.value, ReviewDecision.APPROVE_WITH_EDIT.value}
            }
            classification = classify_predicate(FactPredicate(predicate))
            candidate_values_differ = len({claim.normalized_value for claim in scoped_claims}) >= 2
            if (
                not candidate_values_differ
                and classification.relation.value == "conflicting"
                and len(approved_values) > 1
            ):
                blockers.append(
                    DatabaseSnapshotService._blocker(
                        "inconsistent_approved_values",
                        "Human edits retain multiple values for a single-valued predicate.",
                        predicate=predicate,
                    )
                )
            if not candidate_values_differ:
                continue
            group = session.scalar(
                select(ClaimConflictGroupRecord).where(
                    ClaimConflictGroupRecord.project_id == project_id,
                    ClaimConflictGroupRecord.subject_entity_id == subject_id,
                    ClaimConflictGroupRecord.predicate == predicate,
                    ClaimConflictGroupRecord.scope_fingerprint_sha256 == scope,
                )
            )
            if group is None:
                blockers.append(
                    DatabaseSnapshotService._blocker(
                        "unreconciled_conflicts",
                        "Differing values must be reconciled before publication.",
                        predicate=predicate,
                    )
                )
                continue
            if group.status == "open":
                continue
            if classification.relation.value == "conflicting" and len(approved_values) > 1:
                blockers.append(
                    DatabaseSnapshotService._blocker(
                        "inconsistent_closed_conflict",
                        "Current reviews retain multiple values for a single-valued predicate.",
                        conflict_group_id=str(group.id),
                        predicate=predicate,
                    )
                )

    def _member_payload(
        self,
        session: Session,
        claim: KnowledgeClaimRecord,
        review: ClaimReviewRecord,
        entity_revision: KnowledgeEntityRevisionRecord | None,
    ) -> dict[str, object]:
        entity = session.get(KnowledgeEntityRecord, claim.subject_entity_id)
        if entity is None:
            raise SnapshotServiceConflictError("snapshot Claim subject is missing")
        spans = list(
            session.scalars(
                select(ClaimEvidenceSpanRecord)
                .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
                .order_by(ClaimEvidenceSpanRecord.ordinal)
            )
        )
        if not spans:
            raise SnapshotServiceConflictError("approved snapshot Claim has no exact evidence")
        evidence: list[dict[str, object]] = []
        for span in spans:
            version = session.get(SourceVersionRecord, span.source_version_id)
            source = session.get(SourceRecord, version.source_id) if version else None
            if version is None or source is None or source.project_id != claim.project_id:
                raise SnapshotServiceConflictError("snapshot evidence lineage is incomplete")
            evidence.append(
                {
                    "source_id": str(source.id),
                    "source_version_id": str(version.id),
                    "source_version_number": version.version_number,
                    "source_url": source.canonical_url,
                    "source_title": version.title,
                    "locale": source.locale,
                    "region": source.region,
                    "fetched_at": version.fetched_at.isoformat(),
                    "ordinal": span.ordinal,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "quote": span.quote,
                    "quote_sha256": span.quote_sha256,
                }
            )
        return {
            "sort_key": ":".join(
                [
                    entity.canonical_key,
                    claim.predicate,
                    claim.scope_fingerprint_sha256,
                    review.approved_normalized_value or "",
                    str(claim.id),
                ]
            ),
            "claim_id": str(claim.id),
            "review_id": str(review.id),
            "subject": {
                "entity_id": str(entity.id),
                "canonical_key": entity.canonical_key,
                "entity_revision_id": str(entity_revision.id) if entity_revision else None,
                "revision_number": entity_revision.revision_number if entity_revision else 0,
                "display_name": (
                    entity_revision.display_name if entity_revision else entity.display_name
                ),
            },
            "predicate": claim.predicate,
            "value_kind": review.approved_value_kind,
            "value": review.approved_value,
            "normalized_value": review.approved_normalized_value,
            "locale": claim.locale,
            "region": claim.region,
            "effective_from": claim.effective_from.isoformat() if claim.effective_from else None,
            "effective_to": claim.effective_to.isoformat() if claim.effective_to else None,
            "game_version": claim.game_version,
            "review": {
                "decision": review.decision,
                "reason": review.reason,
                "reviewer_id": review.reviewer_id,
                "created_at": review.created_at.isoformat(),
            },
            "evidence": evidence,
        }

    def _serialize_snapshot(
        self,
        session: Session,
        snapshot: KnowledgeSnapshotRecord,
        *,
        is_latest: bool,
    ) -> dict[str, object]:
        links = list(
            session.scalars(
                select(KnowledgeSnapshotMemberRecord)
                .where(KnowledgeSnapshotMemberRecord.snapshot_id == snapshot.id)
                .order_by(
                    KnowledgeSnapshotMemberRecord.created_at, KnowledgeSnapshotMemberRecord.id
                )
            )
        )
        members: list[dict[str, object]] = []
        for link in links:
            claim = session.get(KnowledgeClaimRecord, link.claim_id)
            review = session.get(ClaimReviewRecord, link.review_id)
            if claim is None or review is None:
                raise SnapshotServiceConflictError("published snapshot lineage is incomplete")
            entity_revision = (
                session.get(KnowledgeEntityRevisionRecord, link.entity_revision_id)
                if link.entity_revision_id
                else None
            )
            if link.entity_revision_id and entity_revision is None:
                raise SnapshotServiceConflictError("published entity revision is missing")
            payload = self._member_payload(session, claim, review, entity_revision)
            members.append(payload)
        members.sort(key=lambda item: str(item["sort_key"]))
        for member in members:
            member.pop("sort_key")
        return {
            "id": str(snapshot.id),
            "project_id": str(snapshot.project_id),
            "version_number": snapshot.version_number,
            "is_latest": is_latest,
            "schema_version": snapshot.schema_version,
            "content_sha256": snapshot.content_sha256,
            "member_count": len(members),
            "members": members,
            "published_by": snapshot.published_by,
            "notes": snapshot.notes,
            "published_at": snapshot.published_at.isoformat(),
        }

    @staticmethod
    def _blocker(code: str, message: str, **context: object) -> dict[str, object]:
        return {"code": code, "message": message, **context}

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
