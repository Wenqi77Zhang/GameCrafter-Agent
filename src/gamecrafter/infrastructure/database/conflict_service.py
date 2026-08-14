"""Deterministic, project-scoped conflict reconciliation and delivery."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.domain.knowledge.claims import FactPredicate
from gamecrafter.domain.knowledge.conflicts import CONFLICT_POLICY_VERSION, classify_predicate
from gamecrafter.infrastructure.database.knowledge_repository import DatabaseKnowledgeRepository
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
    KnowledgeClaimRecord,
    ProjectRecord,
)


class ConflictServiceNotFoundError(LookupError):
    """Raised when a project or conflict read target does not exist."""


class DatabaseConflictService:
    """Group differing immutable claims without model judgment or auto-resolution."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._claims = DatabaseKnowledgeRepository(session_factory)
        self._workspace = DatabaseKnowledgeWorkspaceService(session_factory)

    def reconcile(self, *, project_id: UUID, actor_id: str) -> dict[str, object]:
        """Idempotently create open groups and missing memberships for differing values."""

        created_groups = 0
        created_members = 0
        skipped_closed_groups = 0
        compared_scopes = 0
        with self._session_factory.begin() as session:
            project = session.scalar(
                select(ProjectRecord).where(ProjectRecord.id == project_id).with_for_update()
            )
            if project is None:
                raise ConflictServiceNotFoundError("project not found")
            claims = list(
                session.scalars(
                    select(KnowledgeClaimRecord)
                    .where(KnowledgeClaimRecord.project_id == project_id)
                    .order_by(KnowledgeClaimRecord.created_at, KnowledgeClaimRecord.id)
                )
            )
            grouped: dict[tuple[UUID, str, str], list[KnowledgeClaimRecord]] = defaultdict(list)
            for claim in claims:
                grouped[
                    (claim.subject_entity_id, claim.predicate, claim.scope_fingerprint_sha256)
                ].append(claim)

            for (subject_id, predicate_value, scope_fingerprint), candidates in grouped.items():
                if len({claim.normalized_value for claim in candidates}) < 2:
                    continue
                compared_scopes += 1
                group = session.scalar(
                    select(ClaimConflictGroupRecord).where(
                        ClaimConflictGroupRecord.project_id == project_id,
                        ClaimConflictGroupRecord.subject_entity_id == subject_id,
                        ClaimConflictGroupRecord.predicate == predicate_value,
                        ClaimConflictGroupRecord.scope_fingerprint_sha256 == scope_fingerprint,
                    )
                )
                if group is None:
                    group = ClaimConflictGroupRecord(
                        project_id=project_id,
                        subject_entity_id=subject_id,
                        predicate=predicate_value,
                        scope_fingerprint_sha256=scope_fingerprint,
                        status="open",
                    )
                    session.add(group)
                    session.flush()
                    created_groups += 1
                elif group.status != "open":
                    skipped_closed_groups += 1
                    continue

                existing_claim_ids = set(
                    session.scalars(
                        select(ClaimConflictMemberRecord.claim_id).where(
                            ClaimConflictMemberRecord.conflict_group_id == group.id
                        )
                    )
                )
                classification = classify_predicate(FactPredicate(predicate_value))
                for claim in candidates:
                    if claim.id in existing_claim_ids:
                        continue
                    session.add(
                        ClaimConflictMemberRecord(
                            conflict_group_id=group.id,
                            claim_id=claim.id,
                            relation=classification.relation.value,
                            basis=classification.basis,
                        )
                    )
                    created_members += 1

            session.add(
                AuditEventRecord(
                    project_id=project_id,
                    event_type="knowledge.conflicts_reconciled",
                    actor_type="human",
                    actor_id=actor_id,
                    payload={
                        "policy_version": CONFLICT_POLICY_VERSION,
                        "compared_scopes": compared_scopes,
                        "created_groups": created_groups,
                        "created_members": created_members,
                        "skipped_closed_groups": skipped_closed_groups,
                    },
                )
            )
        return {
            "policy_version": CONFLICT_POLICY_VERSION,
            "compared_scopes": compared_scopes,
            "created_groups": created_groups,
            "created_members": created_members,
            "skipped_closed_groups": skipped_closed_groups,
        }

    def list_conflicts(
        self,
        project_id: UUID,
        *,
        status: str | None = None,
        subject_entity_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Return groups with enriched candidate and exact-evidence read models."""

        with self._session_factory() as session:
            if session.get(ProjectRecord, project_id) is None:
                raise ConflictServiceNotFoundError("project not found")
            statement = select(ClaimConflictGroupRecord).where(
                ClaimConflictGroupRecord.project_id == project_id
            )
            if status is not None:
                statement = statement.where(ClaimConflictGroupRecord.status == status)
            if subject_entity_id is not None:
                statement = statement.where(
                    ClaimConflictGroupRecord.subject_entity_id == subject_entity_id
                )
            groups = list(
                session.scalars(
                    statement.order_by(
                        ClaimConflictGroupRecord.created_at,
                        ClaimConflictGroupRecord.id,
                    )
                )
            )
            memberships = {
                group.id: list(
                    session.scalars(
                        select(ClaimConflictMemberRecord)
                        .where(ClaimConflictMemberRecord.conflict_group_id == group.id)
                        .order_by(
                            ClaimConflictMemberRecord.created_at,
                            ClaimConflictMemberRecord.id,
                        )
                    )
                )
                for group in groups
            }

        claim_by_id = {
            UUID(str(claim["id"])): claim for claim in self._claims.list_claims(project_id)
        }
        entity_by_id = {
            UUID(str(entity["id"])): entity
            for entity in self._workspace.list_entities(project_id, include_archived=True)
        }
        items: list[dict[str, object]] = []
        for group in groups:
            members = memberships[group.id]
            delivered_members = [
                {
                    "relation": member.relation,
                    "basis": member.basis,
                    "claim": claim_by_id[member.claim_id],
                }
                for member in members
            ]
            items.append(
                {
                    "id": str(group.id),
                    "project_id": str(group.project_id),
                    "subject_entity_id": str(group.subject_entity_id),
                    "subject": entity_by_id.get(group.subject_entity_id),
                    "predicate": group.predicate,
                    "scope_fingerprint_sha256": group.scope_fingerprint_sha256,
                    "status": group.status,
                    "policy_version": CONFLICT_POLICY_VERSION,
                    "member_count": len(delivered_members),
                    "distinct_value_count": len(
                        {str(member["claim"]["normalized_value"]) for member in delivered_members}
                    ),
                    "members": delivered_members,
                    "resolution_summary": group.resolution_summary,
                    "resolved_by": group.resolved_by,
                    "resolved_at": (
                        group.resolved_at.isoformat() if group.resolved_at is not None else None
                    ),
                    "created_at": group.created_at.isoformat(),
                }
            )
        return items
