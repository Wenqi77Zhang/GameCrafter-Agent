"""Zero-paid-API trend connectors with bounded responses and explicit provenance."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx2

_GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_YOUTUBE_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
_GOOGLE_NEWS_ENDPOINT = "https://news.google.com/rss/search"
_TITLE_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class ConnectorError(RuntimeError):
    """A safe public-connector failure suitable for a user-facing retry."""


@dataclass(frozen=True, slots=True)
class TrendObservation:
    """One normalized observation ready for the immutable trend ledger."""

    source_name: str
    source_url: str
    observed_at: datetime
    region: str
    signal_type: Literal["topic", "search"]
    title: str
    keywords: tuple[str, ...]
    notes: str
    external_id: str


class PublicTrendConnector:
    """Fetch only documented fixed-host APIs; never accept an arbitrary upstream URL."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 45,
        max_bytes: int = 2 * 1024 * 1024,
        client_factory: Callable[[], httpx2.Client] | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._client_factory = client_factory or self._client

    def gdelt(
        self,
        *,
        query: str,
        region: str,
        max_results: int,
        lookback_hours: int,
    ) -> list[TrendObservation]:
        clean_query = self._query(query)
        clean_region = self._region(region)
        limit = self._limit(max_results)
        if lookback_hours < 1 or lookback_hours > 168:
            raise ConnectorError("lookback hours must be between 1 and 168")
        parameters = {
            "query": clean_query,
            "mode": "artlist",
            "maxrecords": limit,
            "format": "json",
            "sort": "datedesc",
            "timespan": f"{lookback_hours}h",
        }
        url = f"{_GDELT_ENDPOINT}?{urlencode(parameters)}"
        payload = self._json(url)
        articles = payload.get("articles")
        if not isinstance(articles, list):
            raise ConnectorError("GDELT returned an invalid article list")
        observations: list[TrendObservation] = []
        for item in articles[:limit]:
            if not isinstance(item, dict):
                continue
            title = self._text(item.get("title"), 300)
            source_url = self._https(item.get("url"))
            seen = self._timestamp(item.get("seendate"))
            if not title or not source_url or seen is None:
                continue
            domain = self._text(item.get("domain"), 120) or "indexed publisher"
            language = self._text(item.get("language"), 40) or "unknown"
            observations.append(
                TrendObservation(
                    source_name=f"GDELT · {domain}",
                    source_url=source_url,
                    observed_at=seen,
                    region=clean_region,
                    signal_type="topic",
                    title=title,
                    keywords=self._keywords(title),
                    notes=(
                        "Automatically discovered through the GDELT DOC 2.0 public news index; "
                        f"publisher language: {language}. The source article remains the evidence."
                    ),
                    external_id=source_url,
                )
            )
        return observations

    def google_news(
        self,
        *,
        query: str,
        region: str,
        max_results: int,
        lookback_hours: int,
    ) -> list[TrendObservation]:
        clean_query = self._query(query)
        clean_region = self._region(region)
        limit = self._limit(max_results)
        if lookback_hours < 1 or lookback_hours > 168:
            raise ConnectorError("lookback hours must be between 1 and 168")
        parameters = {
            "q": f"{clean_query} when:{max(1, lookback_hours // 24)}d",
            "hl": "en-US",
            "gl": clean_region,
            "ceid": f"{clean_region}:en",
        }
        body = self._bytes(
            f"{_GOOGLE_NEWS_ENDPOINT}?{urlencode(parameters)}",
            accept="application/rss+xml, application/xml, text/xml",
        )
        if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise ConnectorError("RSS provider returned forbidden XML declarations")
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            raise ConnectorError("RSS provider returned invalid XML") from error
        observations: list[TrendObservation] = []
        for item in root.findall("./channel/item")[:limit]:
            title = self._text(item.findtext("title"), 300)
            source_url = self._https(item.findtext("link"))
            published = self._rfc_timestamp(item.findtext("pubDate"))
            source_element = item.find("source")
            publisher = (
                self._text(
                    source_element.text if source_element is not None else None,
                    120,
                )
                or "indexed publisher"
            )
            if not title or not source_url or published is None:
                continue
            observations.append(
                TrendObservation(
                    source_name=f"Google News RSS · {publisher}",
                    source_url=source_url,
                    observed_at=published,
                    region=clean_region,
                    signal_type="topic",
                    title=title,
                    keywords=self._keywords(title),
                    notes=(
                        "Automatically discovered through the public Google News RSS search feed. "
                        "The linked feed item and named publisher remain the evidence."
                    ),
                    external_id=source_url,
                )
            )
        return observations

    def youtube(
        self,
        *,
        api_key: str,
        query: str,
        region: str,
        max_results: int,
        published_after: datetime,
    ) -> list[TrendObservation]:
        key = api_key.strip()
        if not key:
            raise ConnectorError("YouTube connector requires a local API key")
        clean_query = self._query(query)
        clean_region = self._region(region)
        limit = self._limit(max_results)
        after = (
            published_after.astimezone(UTC)
            if published_after.tzinfo
            else published_after.replace(tzinfo=UTC)
        )
        parameters = {
            "part": "snippet",
            "type": "video",
            "order": "date",
            "safeSearch": "moderate",
            "q": clean_query,
            "regionCode": clean_region,
            "relevanceLanguage": "en",
            "publishedAfter": after.isoformat().replace("+00:00", "Z"),
            "maxResults": limit,
            "key": key,
        }
        url = f"{_YOUTUBE_ENDPOINT}?{urlencode(parameters)}"
        payload = self._json(url)
        items = payload.get("items")
        if not isinstance(items, list):
            raise ConnectorError("YouTube returned an invalid search result")
        observations: list[TrendObservation] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            identity = item.get("id") if isinstance(item.get("id"), dict) else {}
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            video_id = self._text(identity.get("videoId"), 32)
            title = self._text(snippet.get("title"), 300)
            published = self._timestamp(snippet.get("publishedAt"))
            if not video_id or not title or published is None:
                continue
            channel = self._text(snippet.get("channelTitle"), 120) or "unknown channel"
            observations.append(
                TrendObservation(
                    source_name=f"YouTube Data API · {channel}",
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    observed_at=published,
                    region=clean_region,
                    signal_type="search",
                    title=title,
                    keywords=self._keywords(title),
                    notes=(
                        "Automatically discovered with the official YouTube Data API search.list "
                        "endpoint. Search rank is not presented as a popularity metric."
                    ),
                    external_id=video_id,
                )
            )
        return observations

    def _json(self, url: str) -> dict[str, Any]:
        try:
            body = self._bytes(url, accept="application/json")
            if b"limit requests" in body.lower():
                raise ConnectorError("GDELT rate limit reached; retry after at least 5 seconds")
            payload = httpx2.Response(200, content=body).json()
        except ConnectorError:
            raise
        except Exception as error:
            safe_url = re.sub(r"([?&]key=)[^&]+", r"\1[redacted]", url)
            raise ConnectorError(
                f"trend provider request failed: {safe_url.split('?')[0]}"
            ) from error
        if not isinstance(payload, dict):
            raise ConnectorError("trend provider returned non-object JSON")
        return payload

    def _bytes(self, url: str, *, accept: str) -> bytes:
        try:
            with self._client_factory() as client:
                response = client.get(
                    url,
                    timeout=self._timeout,
                    headers={"Accept": accept},
                )
                if response.status_code < 200 or response.status_code >= 300:
                    raise ConnectorError(f"trend provider returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared and int(declared) > self._max_bytes:
                    raise ConnectorError("trend provider response exceeded the byte limit")
                body = response.content
                if len(body) > self._max_bytes:
                    raise ConnectorError("trend provider response exceeded the byte limit")
                return body
        except ConnectorError:
            raise
        except Exception as error:
            safe_url = re.sub(r"([?&]key=)[^&]+", r"\1[redacted]", url)
            raise ConnectorError(
                f"trend provider request failed: {safe_url.split('?')[0]}"
            ) from error

    @staticmethod
    def _client() -> httpx2.Client:
        return httpx2.Client(follow_redirects=False, trust_env=False, cookies={})

    @staticmethod
    def _query(value: str) -> str:
        clean = " ".join(value.split())
        if len(clean) < 2 or len(clean) > 160:
            raise ConnectorError("trend query must contain 2 to 160 characters")
        return clean

    @staticmethod
    def _region(value: str) -> str:
        clean = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", clean):
            raise ConnectorError("connector region must be an ISO two-letter code")
        return clean

    @staticmethod
    def _limit(value: int) -> int:
        if value < 1 or value > 50:
            raise ConnectorError("connector result limit must be between 1 and 50")
        return value

    @staticmethod
    def _https(value: object) -> str | None:
        clean = str(value or "").strip()
        return clean if clean.startswith("https://") and len(clean) <= 2048 else None

    @staticmethod
    def _text(value: object, maximum: int) -> str | None:
        clean = " ".join(str(value or "").split())
        return clean[:maximum] if clean else None

    @staticmethod
    def _keywords(title: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(token.casefold() for token in _TITLE_TOKEN.findall(title)))[:20]

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
            try:
                return datetime.strptime(text, pattern).replace(tzinfo=UTC)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _rfc_timestamp(value: object) -> datetime | None:
        try:
            parsed = parsedate_to_datetime(str(value or ""))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
