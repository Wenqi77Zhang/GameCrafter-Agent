from datetime import UTC, datetime

import httpx2
import pytest

from gamecrafter.infrastructure.trends.connectors import ConnectorError, PublicTrendConnector


def _client(payload: dict, *, status: int = 200) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host in {"api.gdeltproject.org", "www.googleapis.com"}
        return httpx2.Response(status, json=payload, request=request)

    return httpx2.Client(transport=httpx2.MockTransport(handler), trust_env=False)


def test_gdelt_connector_preserves_article_provenance_and_time() -> None:
    connector = PublicTrendConnector(
        client_factory=lambda: _client(
            {
                "articles": [
                    {
                        "url": "https://example.com/games/cozy-city",
                        "title": "Cozy open-world games are having a moment",
                        "seendate": "20260826T010203Z",
                        "domain": "example.com",
                        "language": "English",
                    }
                ]
            }
        )
    )

    observations = connector.gdelt(
        query="open world game",
        region="us",
        max_results=10,
        lookback_hours=24,
    )

    assert len(observations) == 1
    item = observations[0]
    assert item.source_name == "GDELT · example.com"
    assert item.source_url == "https://example.com/games/cozy-city"
    assert item.region == "US"
    assert item.observed_at == datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)
    assert "GDELT DOC 2.0" in item.notes


def test_youtube_connector_uses_official_video_identity_without_claiming_views() -> None:
    connector = PublicTrendConnector(
        client_factory=lambda: _client(
            {
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "NTE combat preview",
                            "publishedAt": "2026-08-25T12:00:00Z",
                            "channelTitle": "Creator",
                        },
                    }
                ]
            }
        )
    )

    observations = connector.youtube(
        api_key="local-test-key",
        query="NTE gameplay",
        region="US",
        max_results=5,
        published_after=datetime(2026, 8, 24, tzinfo=UTC),
    )

    assert observations[0].source_url == "https://www.youtube.com/watch?v=abc123"
    assert "not presented as a popularity metric" in observations[0].notes


def test_google_news_rss_connector_parses_bounded_attributed_items() -> None:
    body = b"""<?xml version='1.0'?><rss><channel><item>
    <title>Anime open-world games trend upward</title>
    <link>https://news.google.com/rss/articles/example</link>
    <pubDate>Tue, 25 Aug 2026 12:00:00 GMT</pubDate>
    <source>Games Publisher</source></item></channel></rss>"""

    def factory() -> httpx2.Client:
        return httpx2.Client(
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, content=body, request=request)
            ),
            trust_env=False,
        )

    observations = PublicTrendConnector(client_factory=factory).google_news(
        query="anime open world games",
        region="US",
        max_results=5,
        lookback_hours=24,
    )

    assert observations[0].source_name == "Google News RSS · Games Publisher"
    assert observations[0].observed_at == datetime(2026, 8, 25, 12, tzinfo=UTC)
    assert observations[0].source_url.startswith("https://news.google.com/")


def test_connector_rejects_invalid_bounds_and_redacts_provider_failures() -> None:
    connector = PublicTrendConnector(client_factory=lambda: _client({}, status=503))
    with pytest.raises(ConnectorError, match="HTTP 503"):
        connector.gdelt(query="game trend", region="US", max_results=5, lookback_hours=24)
    with pytest.raises(ConnectorError, match="ISO two-letter"):
        connector.gdelt(query="game trend", region="GLOBAL", max_results=5, lookback_hours=24)
