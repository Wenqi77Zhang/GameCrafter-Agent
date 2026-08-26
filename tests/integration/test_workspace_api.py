from uuid import UUID

from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app
from gamecrafter.api.routes import workspace
from gamecrafter.infrastructure.database.workspace_service import WorkspaceConflictError

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("30000000-0000-0000-0000-000000000001")


class FakeWorkspace:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def list_projects(self):
        return []

    def create_project(self, **kwargs):
        return {
            "id": str(PROJECT_ID),
            "slug": kwargs["slug"],
            "name": kwargs["name"],
            "default_locale": kwargs["default_locale"],
            "created_at": "2026-07-29T00:00:00+00:00",
        }, True

    def list_sources(self, project_id):
        return []

    def list_candidates(self, project_id):
        return []

    def list_runs(self, project_id):
        return []

    def project_overview(self, project_id):
        return {
            "project_id": str(project_id),
            "release": "M5",
            "next_action": "sources",
            "stages": [{"key": "sources", "status": "not_started"}],
            "metrics": {"api_cost_usd": 0},
        }

    def enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return {
            "id": str(RUN_ID),
            "project_id": str(PROJECT_ID),
            "workflow_kind": kwargs["task_type"],
            "task_type": kwargs["task_type"],
            "status": "queued",
            "checkpoint": "created",
            "last_error_code": None,
            "last_error_detail": None,
            "created_at": "2026-07-29T00:00:00+00:00",
            "updated_at": "2026-07-29T00:00:00+00:00",
            "finished_at": None,
        }, True

    def get_run(self, run_id):
        return {}

    def retry_run(self, **kwargs):
        return {
            "id": str(kwargs["run_id"]),
            "project_id": str(PROJECT_ID),
            "workflow_kind": "source.discover",
            "task_type": "source.discover",
            "status": "queued",
            "checkpoint": "source.discover",
            "last_error_code": None,
            "last_error_detail": None,
            "created_at": "2026-07-29T00:00:00+00:00",
            "updated_at": "2026-07-29T00:01:00+00:00",
            "finished_at": None,
        }, True

    def events_after(self, run_id, cursor):
        if cursor is not None and cursor != EVENT_ID:
            raise WorkspaceConflictError("event cursor does not belong to this run")
        return [
            {
                "id": str(EVENT_ID),
                "event_type": "job.completed",
                "actor_type": "worker",
                "payload": {"task_type": "source.capture"},
                "occurred_at": "2026-07-29T00:00:01+00:00",
            }
        ], True


class FakeLocalSourceService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def import_text(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "source_id": "local-source-1",
            "source_version_id": "local-version-1",
            "version_number": 1,
            "private": True,
            "document_kind": kwargs["kind"],
        }, True


def test_workspace_commands_require_explicit_idempotency_and_human_candidate() -> None:
    fake = FakeWorkspace()
    original = workspace._service
    workspace._service = lambda: fake
    try:
        client = TestClient(create_app())
        missing_key = client.post(
            f"/api/projects/{PROJECT_ID}/source-imports",
            json={"candidate_id": "40000000-0000-0000-0000-000000000001"},
        )
        assert missing_key.status_code == 422

        response = client.post(
            f"/api/projects/{PROJECT_ID}/source-imports",
            headers={"Idempotency-Key": "candidate-import-0001"},
            json={"candidate_id": "40000000-0000-0000-0000-000000000001"},
        )
        assert response.status_code == 202
        assert response.json()["workflow_kind"] == "source.capture"
        assert fake.enqueued[0]["task_type"] == "source.capture"
        assert fake.enqueued[0]["candidate_id"] == UUID("40000000-0000-0000-0000-000000000001")
    finally:
        workspace._service = original


def test_project_overview_exposes_guided_progress_without_mutation() -> None:
    fake = FakeWorkspace()
    original = workspace._service
    workspace._service = lambda: fake
    try:
        response = TestClient(create_app()).get(f"/api/projects/{PROJECT_ID}/overview")
        assert response.status_code == 200
        assert response.json()["next_action"] == "sources"
        assert response.json()["metrics"]["api_cost_usd"] == 0
    finally:
        workspace._service = original


def test_private_local_source_import_is_explicit_and_idempotent() -> None:
    fake = FakeLocalSourceService()
    original = workspace._local_source_service
    workspace._local_source_service = lambda: fake
    try:
        response = TestClient(create_app()).post(
            f"/api/projects/{PROJECT_ID}/local-sources",
            headers={"Idempotency-Key": "local-source-command"},
            json={
                "document_key": "nte-transcript",
                "kind": "transcript",
                "title": "NTE interview",
                "filename": "nte.vtt",
                "content": "WEBVTT\n\nWelcome to Hethereau.",
                "media_type": "text/vtt",
                "locale": "en",
                "region": "private",
            },
        )
        assert response.status_code == 201
        assert response.json()["private"] is True
        assert fake.calls[0]["command_key"] == "local-source-command"
    finally:
        workspace._local_source_service = original


def test_failed_run_retry_requires_an_explicit_idempotency_key() -> None:
    fake = FakeWorkspace()
    original = workspace._service
    workspace._service = lambda: fake
    try:
        client = TestClient(create_app())
        assert client.post(f"/api/runs/{RUN_ID}/retry").status_code == 422
        response = client.post(
            f"/api/runs/{RUN_ID}/retry",
            headers={"Idempotency-Key": "manual-retry-0001"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
    finally:
        workspace._service = original


def test_discovery_rejects_unbounded_or_ambiguous_requests() -> None:
    fake = FakeWorkspace()
    original = workspace._service
    workspace._service = lambda: fake
    try:
        client = TestClient(create_app())
        response = client.post(
            f"/api/projects/{PROJECT_ID}/source-discoveries",
            headers={"Idempotency-Key": "discovery-request-0001"},
            json={
                "mode": "quick",
                "listing_urls": [
                    "https://nte.perfectworld.com/en/article/news/index.html",
                    "https://nte.perfectworld.com/cn/article/news/index.html",
                ],
                "candidate_limit": 101,
            },
        )
        assert response.status_code == 422
        assert fake.enqueued == []
    finally:
        workspace._service = original


def test_terminal_sse_stream_contains_a_resumable_event_id() -> None:
    fake = FakeWorkspace()
    original = workspace._service
    workspace._service = lambda: fake
    try:
        client = TestClient(create_app())
        response = client.get(f"/api/runs/{RUN_ID}/events")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert f"id: {EVENT_ID}" in response.text
        assert "event: audit" in response.text
        assert '"event_type":"job.completed"' in response.text

        invalid_cursor = client.get(
            f"/api/runs/{RUN_ID}/events",
            headers={"Last-Event-ID": "50000000-0000-0000-0000-000000000001"},
        )
        assert invalid_cursor.status_code == 409
    finally:
        workspace._service = original
