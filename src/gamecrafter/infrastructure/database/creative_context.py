"""Resolve human-reviewed values and readable source lineage for creative consumers."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gamecrafter.application.creative import CreativeError
from gamecrafter.infrastructure.database.models import (
    ClaimEvidenceSpanRecord,
    ClaimReviewRecord,
    KnowledgeClaimRecord,
    KnowledgeSnapshotMemberRecord,
    SourceRecord,
    SourceVersionRecord,
)


def snapshot_facts(session: Session, snapshot_id: UUID) -> list[dict]:
    members = list(
        session.scalars(
            select(KnowledgeSnapshotMemberRecord)
            .where(KnowledgeSnapshotMemberRecord.snapshot_id == snapshot_id)
            .order_by(KnowledgeSnapshotMemberRecord.id)
        )
    )
    if not members:
        raise CreativeError("创作需要至少一条已审核事实。")
    facts = []
    for member in members:
        claim = session.get(KnowledgeClaimRecord, member.claim_id)
        review = session.get(ClaimReviewRecord, member.review_id)
        if not claim or not review or review.decision not in {"approve", "approve_with_edit"}:
            raise CreativeError("知识快照缺少有效的审核证据。")
        sources = []
        for span in session.scalars(
            select(ClaimEvidenceSpanRecord)
            .where(ClaimEvidenceSpanRecord.claim_id == claim.id)
            .order_by(ClaimEvidenceSpanRecord.ordinal)
        ):
            version = session.get(SourceVersionRecord, span.source_version_id)
            source = session.get(SourceRecord, version.source_id) if version else None
            sources.append(
                {
                    "quote": span.quote,
                    "source_version_id": str(span.source_version_id),
                    "url": source.canonical_url if source else None,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                }
            )
        facts.append(
            {
                "snapshot_member_id": str(member.id),
                "predicate": claim.predicate,
                "value": review.approved_value,
                "locale": claim.locale,
                "region": claim.region,
                "game_version": claim.game_version,
                "sources": sources,
            }
        )
    return facts
