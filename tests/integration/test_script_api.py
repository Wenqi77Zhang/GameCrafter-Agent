from uuid import UUID

from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app
from gamecrafter.api.routes import scripts

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
TASK_ID = UUID("20000000-0000-0000-0000-000000000001")
RUN_ID = UUID("30000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("40000000-0000-0000-0000-000000000001")


class FakeScriptService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_run(self, **kwargs):
        self.calls.append("run")
        return {"id": str(RUN_ID), "marketing_task_id": str(kwargs["marketing_task_id"])}, True

    def list_runs(self, project_id):
        assert project_id == PROJECT_ID
        return [{"id": str(RUN_ID)}]

    def generate(self, **kwargs):
        self.calls.append("generate")
        return {"id": str(VERSION_ID), "origin": "generated"}, True

    def edit(self, **kwargs):
        self.calls.append("edit")
        return {"id": str(VERSION_ID), "origin": "human_edit"}, True

    def evaluate(self, **kwargs):
        self.calls.append("evaluate")
        return {"id": "evaluation-1", "score": 100, "passed": True}, True

    def revise(self, **kwargs):
        self.calls.append("revise")
        return {"id": str(VERSION_ID), "origin": "auto_revision"}, True

    def final_review(self, **kwargs):
        self.calls.append("review")
        return {"id": "review-1", "decision": kwargs["decision"]}, True

    def export(self, **kwargs):
        self.calls.append("export")
        return {"filename": "script.md", "content": "# Script", "sha256": "a" * 64}, True


def test_script_api_exposes_full_human_gated_delivery_flow(monkeypatch) -> None:
    fake = FakeScriptService()
    monkeypatch.setattr(scripts, "_service", lambda: fake)
    client = TestClient(create_app())
    headers = {"Idempotency-Key": "script-api-command"}

    assert (
        client.post(
            f"/api/projects/{PROJECT_ID}/script-runs",
            headers=headers,
            json={"marketing_task_id": str(TASK_ID), "revision_budget": 2, "score_threshold": 80},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/projects/{PROJECT_ID}/script-runs/{RUN_ID}/versions/generate", headers=headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/projects/{PROJECT_ID}/script-runs/{RUN_ID}/versions/{VERSION_ID}/evaluations",
            headers=headers,
        ).json()["passed"]
        is True
    )
    assert (
        client.post(
            f"/api/projects/{PROJECT_ID}/script-runs/{RUN_ID}/final-reviews",
            headers=headers,
            json={"version_id": str(VERSION_ID), "decision": "approve", "reason": "Checked."},
        ).status_code
        == 201
    )
    exported = client.post(
        f"/api/projects/{PROJECT_ID}/script-runs/{RUN_ID}/exports",
        headers=headers,
        json={"version_id": str(VERSION_ID), "format": "markdown"},
    )
    assert exported.status_code == 201 and exported.json()["filename"] == "script.md"
    assert fake.calls == ["run", "generate", "evaluate", "review", "export"]
