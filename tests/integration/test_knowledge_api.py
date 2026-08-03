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

    def list_claims(self, project_id):
        assert project_id == PROJECT_ID
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
