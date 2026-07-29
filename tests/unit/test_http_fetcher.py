import httpx2
import pytest

from gamecrafter.application.ports.source_capture import CaptureRequest
from gamecrafter.domain.knowledge.sources import CaptureMethod
from gamecrafter.infrastructure.ingestion.http import (
    CaptureError,
    HttpPageFetcher,
    ResponseTooLargeError,
    UnsupportedMediaTypeError,
)
from gamecrafter.infrastructure.ingestion.nte import NTE_ACCESS_RULES
from gamecrafter.infrastructure.ingestion.scheduler import HostAccessScheduler
from gamecrafter.security.source_policy import (
    AccessBudget,
    OfficialSourcePolicy,
    UnsupportedSourceError,
)


class PublicResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        return ("8.8.8.8",)


def make_fetcher(handler, *, max_requests: int = 5) -> HttpPageFetcher:
    transport = httpx2.MockTransport(handler)
    return HttpPageFetcher(
        policy=OfficialSourcePolicy(NTE_ACCESS_RULES, resolver=PublicResolver()),
        budget=AccessBudget(max_requests=max_requests),
        scheduler=HostAccessScheduler(
            global_concurrency=1,
            per_host_concurrency=1,
            min_interval_seconds=0,
        ),
        client_factory=lambda: httpx2.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ),
    )


def request(url: str, *, max_bytes: int = 1024) -> CaptureRequest:
    return CaptureRequest(
        url=url,
        max_bytes=max_bytes,
        timeout_seconds=1,
        max_redirects=3,
    )


def test_http_fetcher_captures_html_without_persisting_unsafe_headers() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        assert incoming.headers["user-agent"] == "GameCrafter/0.1"
        return httpx2.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "ETag": '"version-1"',
                "Set-Cookie": "session=secret",
            },
            content=b"<main>official</main>",
        )

    result = make_fetcher(handler).fetch(
        request("https://nte.perfectworld.com/en/main.html?utm_source=test")
    )

    assert result.body == b"<main>official</main>"
    assert result.method is CaptureMethod.HTTP
    assert result.requested_url == "https://nte.perfectworld.com/en/main.html"
    assert result.headers["content-type"] == "text/html; charset=utf-8"
    assert result.headers["etag"] == '"version-1"'
    assert result.headers["content-length"] == "21"
    assert "set-cookie" not in result.headers


def test_http_fetcher_revalidates_redirect_targets() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "https://evil.example/trap"})

    with pytest.raises(UnsupportedSourceError):
        make_fetcher(handler).fetch(request("https://nte.perfectworld.com/en/main.html"))


def test_http_fetcher_allows_bounded_same_site_redirect() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        if incoming.url.path.endswith("index.html"):
            return httpx2.Response(
                302,
                headers={"Location": "/en/article/news/index1.html"},
            )
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"page two",
        )

    result = make_fetcher(handler).fetch(
        request("https://nte.perfectworld.com/en/article/news/index.html")
    )

    assert result.final_url.endswith("/en/article/news/index1.html")
    assert result.body == b"page two"


def test_http_fetcher_stops_streams_over_the_byte_limit() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"12345",
        )

    with pytest.raises(ResponseTooLargeError):
        make_fetcher(handler).fetch(
            request("https://nte.perfectworld.com/en/main.html", max_bytes=4)
        )


def test_http_fetcher_rejects_unexpected_media_type() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "application/octet-stream"},
            content=b"binary",
        )

    with pytest.raises(UnsupportedMediaTypeError):
        make_fetcher(handler).fetch(request("https://nte.perfectworld.com/en/main.html"))


def test_http_fetcher_allows_only_conditional_custom_headers() -> None:
    def handler(incoming: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(304, headers={"ETag": '"same"'})

    fetcher = make_fetcher(handler)
    not_modified = fetcher.fetch(
        CaptureRequest(
            url="https://nte.perfectworld.com/en/main.html",
            max_bytes=10,
            timeout_seconds=1,
            max_redirects=0,
            request_headers={"If-None-Match": '"same"'},
        )
    )
    assert not_modified.status_code == 304
    assert not_modified.body == b""

    with pytest.raises(CaptureError, match="forbidden"):
        fetcher.fetch(
            CaptureRequest(
                url="https://nte.perfectworld.com/en/main.html",
                max_bytes=10,
                timeout_seconds=1,
                max_redirects=0,
                request_headers={"Authorization": "Bearer secret"},
            )
        )
