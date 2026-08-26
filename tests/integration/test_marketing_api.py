from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app
from gamecrafter.api.routes import marketing
from gamecrafter.infrastructure.trends.connectors import TrendObservation

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-0000-0000-000000000001")
TASK_ID = UUID("30000000-0000-0000-0000-000000000001")
CANDIDATE_ID = UUID("40000000-0000-0000-0000-000000000001")


class FakeMarketingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def create_task(self, **kwargs):
        self.calls.append(("task", kwargs))
        return {"id": str(TASK_ID), "knowledge_snapshot_id": str(SNAPSHOT_ID)}, True

    def list_tasks(self, project_id):
        assert project_id == PROJECT_ID
        return [{"id": str(TASK_ID)}]

    def add_signal(self, **kwargs):
        self.calls.append(("signal", kwargs))
        return {"id": "signal-1", "source_url": kwargs["source_url"]}, True

    def list_signals(self, project_id):
        assert project_id == PROJECT_ID
        return [{"id": "signal-1"}]

    def analyze(self, **kwargs):
        self.calls.append(("analyze", kwargs))
        return [{"id": str(CANDIDATE_ID), "score": 100}]

    def list_candidates(self, **kwargs):
        self.calls.append(("list_candidates", kwargs))
        return [{"id": str(CANDIDATE_ID), "status": "unreviewed"}]

    def review_topic(self, **kwargs):
        self.calls.append(("review", kwargs))
        return {"id": "review-1", "decision": kwargs["decision"]}, True


class FakeTrendConnector:
    def gdelt(self, **kwargs):
        assert kwargs["query"] == "open world games"
        return [
            TrendObservation(
                source_name="GDELT · example.com",
                source_url="https://example.com/trend",
                observed_at=datetime(2026, 8, 26, tzinfo=UTC),
                region="US",
                signal_type="topic",
                title="Open-world games",
                keywords=("open", "world", "games"),
                notes="Public index observation.",
                external_id="https://example.com/trend",
            )
        ]


def test_marketing_api_exposes_traceable_trend_to_topic_commands(monkeypatch) -> None:
    fake = FakeMarketingService()
    monkeypatch.setattr(marketing, "_service", lambda: fake)
    client = TestClient(create_app())

    task = client.post(
        f"/api/projects/{PROJECT_ID}/marketing-tasks",
        headers={"Idempotency-Key": "marketing-api-command"},
        json={
            "knowledge_snapshot_id": str(SNAPSHOT_ID),
            "platform": "TikTok",
            "markets": ["US", "UK"],
            "audience": "Potential new players",
            "goal": "Awareness",
            "output_language": "en",
            "duration_seconds": 30,
        },
    )
    assert task.status_code == 201 and task.json()["id"] == str(TASK_ID)
    signal = client.post(
        f"/api/projects/{PROJECT_ID}/trend-signals",
        headers={"Idempotency-Key": "trend-api-command"},
        json={
            "source_name": "TikTok Creative Center",
            "source_url": "https://ads.tiktok.com/business/creativecenter/example",
            "observed_at": datetime.now(UTC).isoformat(),
            "region": "US",
            "signal_type": "hashtag",
            "title": "#NTE",
            "keywords": ["NTE"],
            "metric_name": "posts",
            "metric_value": 1250,
        },
    )
    assert signal.status_code == 201
    analyzed = client.post(f"/api/projects/{PROJECT_ID}/marketing-tasks/{TASK_ID}/topic-analysis")
    assert analyzed.status_code == 200 and analyzed.json()["items"][0]["score"] == 100
    review = client.post(
        f"/api/projects/{PROJECT_ID}/marketing-tasks/{TASK_ID}/topic-candidates/"
        f"{CANDIDATE_ID}/reviews",
        headers={"Idempotency-Key": "topic-api-review"},
        json={"decision": "approve", "reason": "Verified fit and evidence."},
    )
    assert review.status_code == 201 and review.json()["decision"] == "approve"
    assert [name for name, _ in fake.calls] == ["task", "signal", "analyze", "review"]


def test_marketing_api_requires_idempotency_header() -> None:
    client = TestClient(create_app())
    response = client.post(
        f"/api/projects/{PROJECT_ID}/trend-signals",
        json={
            "source_name": "Public source",
            "source_url": "https://example.com/trend",
            "observed_at": "2026-08-15T12:00:00Z",
            "region": "US",
            "signal_type": "topic",
            "title": "Trend",
        },
    )
    assert response.status_code == 422


def test_live_connector_sync_creates_attributed_system_signal(monkeypatch) -> None:
    fake = FakeMarketingService()
    monkeypatch.setattr(marketing, "_service", lambda: fake)
    monkeypatch.setattr(marketing, "_connector", lambda: FakeTrendConnector())
    client = TestClient(create_app())

    catalog = client.get("/api/trend-connectors")
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["key"] == "gdelt-doc"
    response = client.post(
        f"/api/projects/{PROJECT_ID}/trend-connectors/gdelt-doc/sync",
        headers={"Idempotency-Key": "live-connector-sync"},
        json={"query": "open world games", "region": "US", "max_results": 5},
    )

    assert response.status_code == 200
    assert response.json()["inserted"] == 1
    call = fake.calls[-1]
    assert call[0] == "signal"
    assert call[1]["actor_type"] == "system"
    assert call[1]["actor_id"] == "marketing.trend_analyst"
