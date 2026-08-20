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

    def completed_run_for_target(self, **kwargs):
        del kwargs
        return None

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


class FakeReviewService:
    def review_claim(self, **kwargs):
        assert kwargs == {
            "project_id": PROJECT_ID,
            "claim_id": ENTITY_ID,
            "decision": "approve",
            "approved_value": None,
            "reason": "Matches exact evidence.",
            "actor_id": "local-user",
            "command_key": "review-command-1",
        }
        return {
            "id": "40000000-0000-0000-0000-000000000001",
            "claim_id": str(ENTITY_ID),
            "decision": "approve",
        }, True

    def list_reviews(self, project_id, **kwargs):
        assert project_id == PROJECT_ID
        assert kwargs == {"claim_id": ENTITY_ID, "subject_entity_id": None}
        return [{"id": "review-1", "decision": "approve"}]

    def close_conflict(self, **kwargs):
        assert kwargs == {
            "project_id": PROJECT_ID,
            "conflict_group_id": ENTITY_ID,
            "outcome": "resolved",
            "reason": "All members received a final human decision.",
            "actor_id": "local-user",
            "command_key": "closure-command-1",
        }
        return {"id": str(ENTITY_ID), "status": "resolved"}, True


class FakeSnapshotService:
    snapshot = {
        "id": str(RUN_ID),
        "project_id": str(PROJECT_ID),
        "version_number": 1,
        "schema_version": "knowledge-snapshot-v1",
        "content_sha256": "a" * 64,
        "member_count": 1,
        "members": [],
    }

    def readiness(self, project_id):
        assert project_id == PROJECT_ID
        return {
            "publishable": True,
            "schema_version": "knowledge-snapshot-v1",
            "content_sha256": "a" * 64,
            "stats": {"approved_count": 1},
            "blockers": [],
            "next_version_number": 1,
            "latest_snapshot_id": None,
        }

    def publish(self, **kwargs):
        assert kwargs == {
            "project_id": PROJECT_ID,
            "notes": "Reviewed NTE baseline.",
            "actor_id": "local-user",
            "command_key": "snapshot-command-1",
        }
        return self.snapshot, True

    def list_snapshots(self, project_id):
        assert project_id == PROJECT_ID
        return [self.snapshot]

    def get_snapshot(self, **kwargs):
        assert kwargs == {"project_id": PROJECT_ID, "snapshot_id": RUN_ID}
        return self.snapshot


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


def test_human_review_and_conflict_closure_commands_are_project_scoped() -> None:
    reviews = FakeReviewService()
    original = knowledge._reviews
    knowledge._reviews = lambda: reviews
    try:
        client = TestClient(create_app())
        reviewed = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-claims/{ENTITY_ID}/reviews",
            headers={"Idempotency-Key": "review-command-1"},
            json={"decision": "approve", "reason": "Matches exact evidence."},
        )
        listed = client.get(
            f"/api/projects/{PROJECT_ID}/knowledge-reviews",
            params={"claim_id": str(ENTITY_ID)},
        )
        closed = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-conflicts/{ENTITY_ID}/closure",
            headers={"Idempotency-Key": "closure-command-1"},
            json={
                "outcome": "resolved",
                "reason": "All members received a final human decision.",
            },
        )

        assert reviewed.status_code == 201 and reviewed.json()["decision"] == "approve"
        assert listed.status_code == 200 and listed.json()["items"][0]["id"] == "review-1"
        assert closed.status_code == 201 and closed.json()["status"] == "resolved"
    finally:
        knowledge._reviews = original


def test_snapshot_readiness_publication_and_versions_are_project_scoped() -> None:
    snapshots = FakeSnapshotService()
    original = knowledge._snapshots
    knowledge._snapshots = lambda: snapshots
    try:
        client = TestClient(create_app())
        readiness = client.get(f"/api/projects/{PROJECT_ID}/knowledge-snapshot-readiness")
        published = client.post(
            f"/api/projects/{PROJECT_ID}/knowledge-snapshots",
            headers={"Idempotency-Key": "snapshot-command-1"},
            json={"notes": "Reviewed NTE baseline."},
        )
        listed = client.get(f"/api/projects/{PROJECT_ID}/knowledge-snapshots")
        fetched = client.get(f"/api/projects/{PROJECT_ID}/knowledge-snapshots/{RUN_ID}")

        assert readiness.status_code == 200 and readiness.json()["publishable"] is True
        assert published.status_code == 201 and published.json()["version_number"] == 1
        assert listed.status_code == 200 and len(listed.json()["items"]) == 1
        assert fetched.status_code == 200 and fetched.json()["id"] == str(RUN_ID)
    finally:
        knowledge._snapshots = original
