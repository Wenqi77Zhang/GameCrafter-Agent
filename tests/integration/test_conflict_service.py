from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.conflict_service import DatabaseConflictService
from gamecrafter.infrastructure.database.knowledge_workspace_service import (
    DatabaseKnowledgeWorkspaceService,
)
from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    Base,
    ClaimConflictGroupRecord,
    ClaimConflictMemberRecord,
    KnowledgeClaimRecord,
    utc_now,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def _sessions() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _claim(
    *,
    project_id: UUID,
    entity_id: UUID,
    predicate: str,
    value: str,
    scope_fingerprint: str,
) -> KnowledgeClaimRecord:
    normalized = value.strip().casefold()
    return KnowledgeClaimRecord(
        project_id=project_id,
        subject_entity_id=entity_id,
        predicate=predicate,
        value_kind="string",
        value=value,
        normalized_value=normalized,
        value_fingerprint_sha256=sha256(f"string:{normalized}".encode()).hexdigest(),
        scope_fingerprint_sha256=scope_fingerprint,
        confidence=0.9,
        locale="en",
        region="global",
        model_provider="replay",
        model_name="offline-fixture",
        prompt_version="knowledge-claim-v1",
        schema_version="knowledge-claim-v1",
    )


def test_reconciliation_is_deterministic_conservative_and_idempotent() -> None:
    sessions = _sessions()
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"conflict-{uuid4().hex}",
        name="Conflict fixture",
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=["NTE"],
        actor_id="test-user",
    )
    entity_id = UUID(str(entity["id"]))
    scope = sha256(b"en:global:timeless").hexdigest()
    with sessions.begin() as session:
        session.add_all(
            [
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.name",
                    value="Neverness to Everness",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.name",
                    value="NTE",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.name",
                    value="NTE",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.developer",
                    value="Hotta Studio",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.developer",
                    value="Perfect World Games",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="game.alias",
                    value="NTE",
                    scope_fingerprint=scope,
                ),
            ]
        )

    service = DatabaseConflictService(sessions)
    first = service.reconcile(project_id=project_id, actor_id="test-user")
    assert first == {
        "policy_version": "claim-conflict-v1",
        "compared_scopes": 2,
        "created_groups": 2,
        "created_members": 5,
        "skipped_closed_groups": 0,
    }
    second = service.reconcile(project_id=project_id, actor_id="test-user")
    assert second["created_groups"] == 0
    assert second["created_members"] == 0

    delivered = service.list_conflicts(project_id, status="open")
    assert len(delivered) == 2
    by_predicate = {item["predicate"]: item for item in delivered}
    names = by_predicate["game.name"]
    assert names["member_count"] == 3
    assert names["distinct_value_count"] == 2
    assert {member["relation"] for member in names["members"]} == {"conflicting"}
    developers = by_predicate["game.developer"]
    assert developers["member_count"] == 2
    assert {member["relation"] for member in developers["members"]} == {"possibly_coexisting"}
    assert all(member["claim"]["status"] == "candidate_unreviewed" for member in names["members"])

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ClaimConflictGroupRecord)) == 2
        assert session.scalar(select(func.count()).select_from(ClaimConflictMemberRecord)) == 5
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEventRecord)
                .where(AuditEventRecord.event_type == "knowledge.conflicts_reconciled")
            )
            == 2
        )


def test_reconciliation_never_silently_reopens_a_human_closed_group() -> None:
    sessions = _sessions()
    project_id = DatabaseRunService(sessions).create_project(
        slug=f"closed-conflict-{uuid4().hex}",
        name="Closed conflict fixture",
    )
    entity, _ = DatabaseKnowledgeWorkspaceService(sessions).create_entity(
        project_id=project_id,
        display_name="异环",
        aliases=[],
        actor_id="test-user",
    )
    entity_id = UUID(str(entity["id"]))
    scope = sha256(b"closed-scope").hexdigest()
    with sessions.begin() as session:
        session.add_all(
            [
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="release.status",
                    value="announced",
                    scope_fingerprint=scope,
                ),
                _claim(
                    project_id=project_id,
                    entity_id=entity_id,
                    predicate="release.status",
                    value="released",
                    scope_fingerprint=scope,
                ),
            ]
        )
    service = DatabaseConflictService(sessions)
    service.reconcile(project_id=project_id, actor_id="test-user")
    with sessions.begin() as session:
        group = session.scalar(select(ClaimConflictGroupRecord))
        assert group is not None
        group.status = "resolved"
        group.resolution_summary = "Human resolution retained."
        group.resolved_by = "test-user"
        group.resolved_at = utc_now()
        group.resolution_command_key = "test-human-resolution"
        group.resolution_review_counts = {}
    with sessions.begin() as session:
        session.add(
            _claim(
                project_id=project_id,
                entity_id=entity_id,
                predicate="release.status",
                value="in beta",
                scope_fingerprint=scope,
            )
        )

    result = service.reconcile(project_id=project_id, actor_id="test-user")
    assert result["skipped_closed_groups"] == 1
    with sessions() as session:
        group = session.scalar(select(ClaimConflictGroupRecord))
        assert group is not None and group.status == "resolved"
        assert group.resolution_summary == "Human resolution retained."
        assert session.scalar(select(func.count()).select_from(ClaimConflictMemberRecord)) == 2
