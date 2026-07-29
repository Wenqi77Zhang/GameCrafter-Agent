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

    def enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return {
            "id": str(RUN_ID),
            "project_id": str(PROJECT_ID),
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
        assert fake.enqueued[0]["task_type"] == "source.capture"
        assert fake.enqueued[0]["candidate_id"] == UUID("40000000-0000-0000-0000-000000000001")
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
