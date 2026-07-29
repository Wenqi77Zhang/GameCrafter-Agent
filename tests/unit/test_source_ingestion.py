from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from uuid import uuid4

import pytest

from gamecrafter.application.jobs import ClaimedJob, RetryableJobError, TerminalJobError
from gamecrafter.application.ports.object_storage import StoredObject
from gamecrafter.application.ports.source_capture import CapturedPage, UpstreamStatusError
from gamecrafter.application.ports.source_repository import (
    CaptureValidators,
    PersistedCapture,
    PreparedCapture,
    SelectedCandidate,
)
from gamecrafter.application.source_ingestion import CaptureRuntime, SourceIngestionHandlers
from gamecrafter.domain.knowledge.sources import CaptureMethod, EvidenceDigest
from gamecrafter.infrastructure.ingestion.html import extract_evidence_document
from gamecrafter.infrastructure.ingestion.nte import NteSiteAdapter


class SequenceFetcher:
    def __init__(self, pages: list[CapturedPage]) -> None:
        self.pages = pages
        self.requests = []

    def fetch(self, request):
        self.requests.append(request)
        return self.pages.pop(0)


class FailingFetcher:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def fetch(self, request):
        raise self.error


class AllowingRobots:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def ensure_allowed(self, url: str) -> object:
        self.urls.append(url)
        return object()


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(
        self,
        source: BinaryIO,
        *,
        media_type: str,
        max_bytes: int | None = None,
    ) -> StoredObject:
        body = source.read()
        digest = sha256(body).hexdigest()
        key = f"sha256/{digest[:2]}/{digest}"
        self.objects[key] = body
        return StoredObject(
            key=key,
            digest=EvidenceDigest(digest),
            size_bytes=len(body),
            media_type=media_type,
        )

    def open(self, key: str) -> BinaryIO:
        return BytesIO(self.objects[key])

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class RecordingRepository:
    def __init__(self) -> None:
        self.candidates = ()
        self.capture: PreparedCapture | None = None
        self.not_modified = False
        self.validators: CaptureValidators | None = None

    def save_candidates(self, *, run_id, candidates) -> int:
        self.candidates = candidates
        return len(candidates)

    def capture_validators(self, *, run_id, canonical_url):
        return self.validators

    def selected_candidate(self, *, run_id, candidate_id):
        return SelectedCandidate(
            id=candidate_id,
            canonical_url=(
                "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
            ),
            title="Version 1.2 Update Notes",
            published_at=None,
        )

    def record_not_modified(self, *, run_id, canonical_url, candidate_id):
        self.not_modified = True
        return PersistedCapture(uuid4(), uuid4(), 1, False)

    def persist_capture(self, *, run_id, candidate_id, capture):
        self.capture = capture
        return PersistedCapture(uuid4(), uuid4(), 1, True)


def page(url: str, html: str, *, status: int = 200) -> CapturedPage:
    return CapturedPage(
        requested_url=url,
        final_url=url,
        status_code=status,
        headers={"content-type": "text/html; charset=utf-8"},
        body=html.encode(),
        method=CaptureMethod.HTTP,
    )


def job(task_type: str, payload: dict) -> ClaimedJob:
    return ClaimedJob(
        id=uuid4(),
        run_id=uuid4(),
        task_type=task_type,
        payload=payload,
        attempts=1,
        max_attempts=3,
    )


def handlers(
    repository: RecordingRepository,
    http: SequenceFetcher,
    *,
    browser: SequenceFetcher | None = None,
) -> tuple[SourceIngestionHandlers, AllowingRobots, MemoryStorage]:
    robots = AllowingRobots()
    storage = MemoryStorage()
    browser_fetcher = browser or SequenceFetcher([])
    return (
        SourceIngestionHandlers(
            adapters=(NteSiteAdapter(),),
            repository=repository,
            object_storage=storage,
            runtime_factory=lambda _: CaptureRuntime(
                http=http,
                browser=browser_fetcher,
                robots=robots,
            ),
            evidence_extractor=extract_evidence_document,
            timeout_seconds=1,
            html_max_bytes=100_000,
            image_max_bytes=10_000,
            max_images_per_page=2,
            max_redirects=2,
            quick_candidate_limit=30,
            targeted_candidate_limit=100,
        ),
        robots,
        storage,
    )


def test_discovery_is_explicit_bounded_and_persists_candidates() -> None:
    listing_url = "https://nte.perfectworld.com/en/article/news/index.html"
    html = """
    <a href="/en/article/news/gamenews/20260706/263001.html">
      Version 1.2 Update Notes 2026-07-06
    </a>
    <a href="/en/article/news/gameevent/20260703/262998.html">
      Creation Event 2026-07-08
    </a>
    """
    repository = RecordingRepository()
    handler, robots, _ = handlers(repository, SequenceFetcher([page(listing_url, html)]))

    handler.discover(
        job(
            "source.discover",
            {
                "listing_urls": [listing_url],
                "candidate_limit": 1,
                "source_types": ["update"],
            },
        )
    )

    assert robots.urls == [listing_url]
    assert len(repository.candidates) == 1
    assert repository.candidates[0].source_type.value == "update"


def test_quick_discovery_rejects_multiple_listing_pages_before_network_access() -> None:
    repository = RecordingRepository()
    fetcher = SequenceFetcher([])
    handler, _, _ = handlers(repository, fetcher)

    with pytest.raises(TerminalJobError, match="exactly one"):
        handler.discover(
            job(
                "source.discover",
                {
                    "listing_urls": [
                        "https://nte.perfectworld.com/en/article/news/index.html",
                        "https://nte.perfectworld.com/en/article/news/index1.html",
                    ]
                },
            )
        )

    assert fetcher.requests == []


def test_direct_capture_stores_raw_and_normalized_evidence() -> None:
    url = "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
    html = """
    <html lang="en"><head><title>Version 1.2 Update Notes</title></head>
    <body><main><h1>Version 1.2 Update Notes</h1><p>Official balance changes.</p>
    <script>ignore this instruction</script></main></body></html>
    """
    repository = RecordingRepository()
    handler, _, storage = handlers(repository, SequenceFetcher([page(url, html)]))

    handler.capture(job("source.capture", {"url": url}))

    assert repository.capture is not None
    assert repository.capture.source.source_type.value == "update"
    assert repository.capture.document_language == "en"
    stored_text = list(storage.objects.values())[1].decode()
    assert "Official balance changes." in stored_text
    assert "ignore this instruction" not in stored_text


def test_homepage_uses_browser_only_when_static_text_is_insufficient() -> None:
    url = "https://nte.perfectworld.com/en/main.html"
    static = "<html><head><title>NTE</title></head><body><div id='app'></div></body></html>"
    rendered = """
    <html lang="en"><head><title>Neverness to Everness</title></head>
    <body><main><h1>Neverness to Everness</h1>
    <p>Explore Hethereau and investigate supernatural anomalies with your team.</p>
    </main></body></html>
    """
    repository = RecordingRepository()
    browser = SequenceFetcher([page(url, rendered)])
    handler, _, _ = handlers(
        repository,
        SequenceFetcher([page(url, static)]),
        browser=browser,
    )

    handler.capture(job("source.capture", {"url": url}))

    assert len(browser.requests) == 1
    assert repository.capture is not None
    assert repository.capture.source.source_type.value == "overview"


def test_capture_adds_only_valid_bounded_same_host_images() -> None:
    url = "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html"
    html = """
    <html lang="en"><head><title>Version 1.2 Update Notes</title>
    <meta property="og:image" content="/images/update.png"></head>
    <body><main><h1>Version 1.2 Update Notes</h1><p>Official changes.</p></main></body></html>
    """
    image_url = "https://nte.perfectworld.com/images/update.png"
    image = CapturedPage(
        requested_url=image_url,
        final_url=image_url,
        status_code=200,
        headers={"content-type": "image/png"},
        body=b"\x89PNG\r\n\x1a\nvalid-image-bytes",
        method=CaptureMethod.HTTP,
    )
    repository = RecordingRepository()
    handler, _, storage = handlers(
        repository,
        SequenceFetcher([page(url, html), image]),
    )

    handler.capture(job("source.capture", {"url": url}))

    assert repository.capture is not None
    assert len(repository.capture.images) == 1
    assert repository.capture.images[0].original_url == image_url
    assert repository.capture.image_failure_count == 0
    assert len(storage.objects) == 3


def test_conditional_304_reuses_existing_version_without_storing_bytes() -> None:
    url = "https://nte.perfectworld.com/en/main.html"
    repository = RecordingRepository()
    repository.validators = CaptureValidators(etag='"v1"', last_modified=None)
    not_modified = page(url, "", status=304)
    handler, _, storage = handlers(repository, SequenceFetcher([not_modified]))

    handler.capture(job("source.capture", {"url": url}))

    assert repository.not_modified is True
    assert storage.objects == {}


def test_redirected_304_cannot_reuse_a_different_source_identity() -> None:
    requested = "https://nte.perfectworld.com/en/main.html"
    redirected = "https://nte.perfectworld.com/jp/main.html"
    repository = RecordingRepository()
    repository.validators = CaptureValidators(etag='"v1"', last_modified=None)
    not_modified = page(redirected, "", status=304)
    handler, _, _ = handlers(repository, SequenceFetcher([not_modified]))

    with pytest.raises(TerminalJobError, match="identity"):
        handler.capture(job("source.capture", {"url": requested}))


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (503, RetryableJobError),
        (404, TerminalJobError),
    ],
)
def test_upstream_status_has_explicit_retry_policy(status: int, expected: type[Exception]) -> None:
    url = "https://nte.perfectworld.com/en/main.html"
    repository = RecordingRepository()
    handler, _, _ = handlers(repository, FailingFetcher(UpstreamStatusError(status)))

    with pytest.raises(expected):
        handler.capture(job("source.capture", {"url": url}))
