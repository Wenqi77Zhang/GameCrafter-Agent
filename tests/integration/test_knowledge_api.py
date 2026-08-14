from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app
from gamecrafter.api.routes import knowledge
from gamecrafter.application.ports.knowledge_repository import ExtractionTarget
from gamecrafter.config.settings import Settings
from gamecrafter.infrastructure.models.replay_fixtures import load_replay_fixture

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
ENTITY_ID = UUID("20000000-0000-0000-0000-000000000001")
RUN_ID = UUID("30000000-0000-0000-0000-000000000001")
FIXTURE_PATH = Path("fixtures/nte/official-homepage-en-v1.json")


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        loaded = load_replay_fixture(FIXTURE_PATH)
        body = loaded.document.normalized_text.encode("utf-8")
        self.target = ExtractionTarget(
            project_id=PROJECT_ID,
            source_version_id=loaded.document.source_version_id,
            subject_entity_id=ENTITY_ID,
            subject_entity_key=loaded.document.subject_entity_key,
            locale=loaded.document.locale,
            region=loaded.document.region,
            object_key=f"sha256/{sha256(body).hexdigest()[:2]}/{sha256(body).hexdigest()}",
            object_sha256=sha256(body).hexdigest(),
            size_bytes=len(body),
        )

    def validate_target(self, **kwargs):
        assert kwargs["project_id"] == PROJECT_ID
        assert kwargs["source_version_id"] == self.target.source_version_id
        assert kwargs["subject_entity_id"] == ENTITY_ID
        return self.target

    def extraction_result(self, **kwargs):
        return {"run_id": str(kwargs["run_id"]), "claim_count": 2, "invocations": []}

    def list_claims(self, project_id, **kwargs):
        assert project_id == PROJECT_ID
        assert kwargs in (
            {"subject_entity_id": None, "extraction_run_id": None},
            {"subject_entity_id": ENTITY_ID, "extraction_run_id": RUN_ID},
        )
        return [{"id": "claim-1", "evidence": [{"quote": "exact"}]}]


class FakeWorkspace:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return {
            "id": str(RUN_ID),
            "project_id": str(PROJECT_ID),
            "workflow_kind": kwargs["task_type"],
            "task_type": kwargs["task_type"],
            "status": "queued",
        }, True


class FakeKnowledgeWorkspace:
    def __init__(self) -> None:
        self.entity = {
            "id": str(ENTITY_ID),
            "project_id": str(PROJECT_ID),
            "entity_type": "game",
            "canonical_key": "game:nte",
            "display_name": "异环",
            "aliases": ["NTE"],
            "status": "active",
            "revision_number": 1,
        }

    def list_entities(self, project_id, *, include_archived=False):
        assert project_id == PROJECT_ID
        assert include_archived is False
        return [self.entity]

    def create_entity(self, **kwargs):
        assert kwargs["project_id"] == PROJECT_ID
        assert kwargs["actor_id"] == "local-user"
        return self.entity, True

    def correct_entity(self, **kwargs):
        assert kwargs["entity_id"] == ENTITY_ID
        return {**self.entity, "display_name": kwargs["display_name"], "revision_number": 2}, True

    def archive_entity(self, **kwargs):
        assert kwargs["entity_id"] == ENTITY_ID
        return {**self.entity, "status": "archived", "revision_number": 2}, True

    def list_entity_revisions(self, **kwargs):
        assert kwargs["entity_id"] == ENTITY_ID
        return [{"revision_number": 1, "display_name": "异环", "status": "active"}]

    def list_source_versions(self, project_id):
        assert project_id == PROJECT_ID
        return [{"id": str(FakeKnowledgeRepository().target.source_version_id), "is_latest": True}]


class FakeConflictService:
    def reconcile(self, **kwargs):
        assert kwargs == {"project_id": PROJECT_ID, "actor_id": "local-user"}
        return {
            "policy_version": "claim-conflict-v1",
            "compared_scopes": 1,
            "created_groups": 1,
            "created_members": 2,
            "skipped_closed_groups": 0,
        }

    def list_conflicts(self, project_id, **kwargs):
        assert project_id == PROJECT_ID
        assert kwargs == {"status": "open", "subject_entity_id": ENTITY_ID}
        return [
            {
                "id": "conflict-1",
                "predicate": "game.name",
                "status": "open",
                "member_count": 2,
            }
        ]


def test_disabled_mode_blocks_before_enqueue() -> None:
    repository = FakeKnowledgeRepository()
    workspace = FakeWorkspace()
    originals = knowledge._repository, knowledge._workspace, knowledge.get_settings
    knowledge._repository = lambda: repository
    knowledge._workspace = lambda: workspace
    knowledge.get_settings = lambda: Settings(_env_file=None, model_provider="disabled")
    try:
        response = TestClient(create_app()).post(
            f"/api/projects/{PROJECT_ID}/knowledge-extractions",
            headers={"Idempotency-Key": "knowledge-disabled-1"},
            json={
                "source_version_id": str(repository.target.source_version_id),
                "subject_entity_id": str(ENTITY_ID),
            },
        )
        assert response.status_code == 409
        assert "exact local replay" in response.json()["detail"]
        assert workspace.enqueued == []
    finally:
        knowledge._repository, knowledge._workspace, knowledge.get_settings = originals


def test_exact_replay_queues_and_read_models_are_project_scoped() -> None:
    repository = FakeKnowledgeRepository()
    workspace = FakeWorkspace()
    originals = knowledge._repository, knowledge._workspace, knowledge.get_settings
    knowledge._repository = lambda: repository
    knowledge._workspace = lambda: workspace
    knowledge.get_settings = lambda: Settings(
        _env_file=None,
        model_provider="replay",
        model_replay_fixture_path=FIXTURE_PATH,
    )
    try:
        client = TestClient(create_app())
        response = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-extractions",
            headers={"Idempotency-Key": "knowledge-replay-1"},
            json={
                "source_version_id": str(repository.target.source_version_id),
                "subject_entity_id": str(ENTITY_ID),
            },
        )
        assert response.status_code == 202
        assert response.json()["workflow_kind"] == "knowledge.extract"
        assert workspace.enqueued[0]["payload"] == {
            "source_version_id": str(repository.target.source_version_id),
            "subject_entity_id": str(ENTITY_ID),
        }

        result = client.get(f"/api/projects/{PROJECT_ID}/knowledge-extractions/{RUN_ID}")
        claims = client.get(f"/api/projects/{PROJECT_ID}/knowledge-claims")
        assert result.status_code == 200 and result.json()["claim_count"] == 2
        assert claims.status_code == 200 and claims.json()["items"][0]["id"] == "claim-1"
    finally:
        knowledge._repository, knowledge._workspace, knowledge.get_settings = originals


def test_knowledge_delivery_routes_and_replay_capability() -> None:
    repository = FakeKnowledgeRepository()
    delivery = FakeKnowledgeWorkspace()
    originals = knowledge._repository, knowledge._knowledge_workspace, knowledge.get_settings
    knowledge._repository = lambda: repository
    knowledge._knowledge_workspace = lambda: delivery
    knowledge.get_settings = lambda: Settings(
        _env_file=None,
        model_provider="replay",
        model_replay_fixture_path=FIXTURE_PATH,
    )
    try:
        client = TestClient(create_app())
        entities = client.get(f"/api/projects/{PROJECT_ID}/knowledge-entities")
        created = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-entities",
            json={"display_name": "异环", "aliases": ["NTE"]},
        )
        corrected = client.put(
            f"/api/projects/{PROJECT_ID}/knowledge-entities/{ENTITY_ID}",
            json={
                "display_name": "异环（Neverness to Everness）",
                "aliases": ["NTE"],
                "change_reason": "Correct the display label.",
            },
        )
        revisions = client.get(
            f"/api/projects/{PROJECT_ID}/knowledge-entities/{ENTITY_ID}/revisions"
        )
        versions = client.get(f"/api/projects/{PROJECT_ID}/source-versions")
        capability = client.get(
            f"/api/projects/{PROJECT_ID}/knowledge-extraction-capability",
            params={
                "source_version_id": str(repository.target.source_version_id),
                "subject_entity_id": str(ENTITY_ID),
            },
        )
        claims = client.get(
            f"/api/projects/{PROJECT_ID}/knowledge-claims",
            params={
                "subject_entity_id": str(ENTITY_ID),
                "extraction_run_id": str(RUN_ID),
            },
        )
        archived = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-entities/{ENTITY_ID}/archive",
            json={"change_reason": "Created the wrong subject."},
        )

        assert entities.status_code == 200
        assert created.status_code == 201
        assert corrected.status_code == 200 and corrected.json()["revision_number"] == 2
        assert revisions.status_code == 200
        assert versions.status_code == 200 and versions.json()["items"][0]["is_latest"]
        assert capability.status_code == 200
        assert capability.json() == {
            "available": True,
            "mode": "offline_replay",
            "reason_code": "available",
            "reason": "an exact local zero-cost replay is available",
        }
        assert claims.status_code == 200
        assert archived.status_code == 200 and archived.json()["status"] == "archived"
    finally:
        knowledge._repository, knowledge._knowledge_workspace, knowledge.get_settings = originals


def test_deterministic_conflict_reconciliation_and_reads_are_project_scoped() -> None:
    conflicts = FakeConflictService()
    original = knowledge._conflicts
    knowledge._conflicts = lambda: conflicts
    try:
        client = TestClient(create_app())
        reconciled = client.post(f"/api/projects/{PROJECT_ID}/knowledge-conflicts/reconcile")
        listed = client.get(
            f"/api/projects/{PROJECT_ID}/knowledge-conflicts",
            params={"status": "open", "subject_entity_id": str(ENTITY_ID)},
        )

        assert reconciled.status_code == 200
        assert reconciled.json()["created_groups"] == 1
        assert listed.status_code == 200
        assert listed.json()["items"][0]["predicate"] == "game.name"
    finally:
        knowledge._conflicts = original
