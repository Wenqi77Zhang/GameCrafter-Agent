import os
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.conflict_service import DatabaseConflictService
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
    KnowledgeClaimRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService

pytestmark = pytest.mark.postgres


def _postgres_sessions() -> sessionmaker[Session]:
    database_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GAMECRAFTER_TEST_DATABASE_URL is not configured")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True),
        expire_on_commit=False,
    )


def test_real_postgresql_persists_idempotent_deterministic_conflict_groups() -> None:
    sessions = _postgres_sessions()
    nonce = uuid4().hex
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"c3-conflict-{nonce}",
        name="C3 conflict acceptance",
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="c3-test",
    )
    entity_id = UUID(str(entity["id"]))
    scope = sha256(f"scope:{nonce}".encode()).hexdigest()
    with sessions.begin() as session:
        for value in ("Neverness to Everness", "NTE"):
            normalized = value.casefold()
            session.add(
                KnowledgeClaimRecord(
                    project_id=project_id,
                    subject_entity_id=entity_id,
                    predicate="game.name",
                    value_kind="string",
                    value=value,
                    normalized_value=normalized,
                    value_fingerprint_sha256=sha256(normalized.encode()).hexdigest(),
                    scope_fingerprint_sha256=scope,
                    confidence=0.9,
                    locale="en",
                    region="global",
                    model_provider="replay",
                    model_name="offline-fixture",
                    prompt_version="knowledge-claim-v1",
                    schema_version="knowledge-claim-v1",
                )
            )

    service = DatabaseConflictService(sessions)
    first = service.reconcile(project_id=project_id, actor_id="c3-test")
    second = service.reconcile(project_id=project_id, actor_id="c3-test")
    assert first["created_groups"] == 1 and first["created_members"] == 2
    assert second["created_groups"] == 0 and second["created_members"] == 0

    delivered = service.list_conflicts(project_id, status="open")
    assert len(delivered) == 1
    assert delivered[0]["predicate"] == "game.name"
    assert delivered[0]["distinct_value_count"] == 2
    assert {member["relation"] for member in delivered[0]["members"]} == {"conflicting"}
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ClaimConflictGroupRecord)) >= 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(ClaimConflictMemberRecord)
                .join(ClaimConflictGroupRecord)
                .where(ClaimConflictGroupRecord.project_id == project_id)
            )
            == 2
        )
