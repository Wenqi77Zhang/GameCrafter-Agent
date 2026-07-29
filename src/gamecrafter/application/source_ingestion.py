"""Deterministic B3 handlers for source discovery and immutable capture."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urljoin
from uuid import UUID

from gamecrafter.application.jobs import ClaimedJob, RetryableJobError, TerminalJobError
from gamecrafter.application.ports.object_storage import ObjectStorage
from gamecrafter.application.ports.site_adapter import DiscoveredPage, SiteAdapter
from gamecrafter.application.ports.source_capture import (
    BrowserUnavailableError,
    CaptureError,
    CapturePurpose,
    CaptureRequest,
    EvidenceDocument,
    PageFetcher,
    ResponseTooLargeError,
    RobotsDeniedError,
    RobotsPolicy,
    SourceAccessError,
    UnsupportedMediaTypeError,
    UpstreamStatusError,
)
from gamecrafter.application.ports.source_repository import (
    PreparedCapture,
    PreparedImage,
    SourceRepository,
    SourceStateError,
)
from gamecrafter.domain.knowledge.sources import SourceType

DISCOVER_SOURCE_TASK = "source.discover"
CAPTURE_SOURCE_TASK = "source.capture"
PARSER_VERSION = "html-visible-text-v1"
CAPTURE_POLICY_VERSION = "nte-official-v1"
_MIN_BROWSER_FALLBACK_TEXT_CHARS = 80
_MAX_LISTING_URLS = 10


@dataclass(frozen=True, slots=True)
class CaptureRuntime:
    """Per-job request budget shared by robots, HTTP, and browser access."""

    http: PageFetcher
    browser: PageFetcher
    robots: RobotsPolicy


RuntimeFactory = Callable[[int], CaptureRuntime]
EvidenceExtractor = Callable[[str], EvidenceDocument]


class SourceIngestionHandlers:
    """Coordinate adapters, capture, storage, and transactional persistence."""

    def __init__(
        self,
        *,
        adapters: Sequence[SiteAdapter],
        repository: SourceRepository,
        object_storage: ObjectStorage,
        runtime_factory: RuntimeFactory,
        evidence_extractor: EvidenceExtractor,
        timeout_seconds: float,
        html_max_bytes: int,
        image_max_bytes: int,
        max_images_per_page: int,
        max_redirects: int,
        quick_candidate_limit: int,
        targeted_candidate_limit: int,
    ) -> None:
        self._adapters = tuple(adapters)
        self._repository = repository
        self._storage = object_storage
        self._runtime_factory = runtime_factory
        self._extract_document = evidence_extractor
        self._timeout = timeout_seconds
        self._html_max_bytes = html_max_bytes
        self._image_max_bytes = image_max_bytes
        self._max_images = max_images_per_page
        self._max_redirects = max_redirects
        self._quick_limit = quick_candidate_limit
        self._targeted_limit = targeted_candidate_limit

    def discover(self, job: ClaimedJob) -> None:
        """Fetch explicitly supplied listing pages and persist bounded candidates."""

        try:
            payload = _discover_payload(job.payload, self._quick_limit, self._targeted_limit)
            runtime = self._runtime_factory(len(payload.urls) * (self._max_redirects + 4))
            collected: list[DiscoveredPage] = []
            seen: set[str] = set()
            for url in payload.urls:
                adapter = self._adapter_for(url)
                canonical = adapter.canonicalize(url)
                runtime.robots.ensure_allowed(canonical)
                page = runtime.http.fetch(self._request(canonical))
                html = _decode_html(page.body, page.headers.get("content-type"))
                for candidate in adapter.discover(html, page_url=page.final_url):
                    if candidate.canonical_url in seen or not _matches_filters(candidate, payload):
                        continue
                    seen.add(candidate.canonical_url)
                    collected.append(candidate)
                    if len(collected) >= payload.limit:
                        break
                if len(collected) >= payload.limit:
                    break
            self._repository.save_candidates(run_id=job.run_id, candidates=tuple(collected))
        except Exception as error:
            _raise_job_error(error)

    def capture(self, job: ClaimedJob) -> None:
        """Capture one direct URL or one human-selected discovery candidate."""

        try:
            payload = _capture_payload(job.payload)
            candidate = (
                self._repository.selected_candidate(
                    run_id=job.run_id,
                    candidate_id=payload.candidate_id,
                )
                if payload.candidate_id is not None
                else None
            )
            requested_url = candidate.canonical_url if candidate is not None else payload.url
            if requested_url is None:
                raise TerminalJobError("capture requires a URL or selected candidate")
            adapter = self._adapter_for(requested_url)
            canonical = adapter.canonicalize(requested_url)
            runtime = self._runtime_factory(
                (self._max_redirects + 2) * 3 + self._max_images * (self._max_redirects + 1)
            )
            runtime.robots.ensure_allowed(canonical)

            validators = self._repository.capture_validators(
                run_id=job.run_id,
                canonical_url=canonical,
            )
            request_headers = {}
            if validators is not None:
                if validators.etag:
                    request_headers["If-None-Match"] = validators.etag
                if validators.last_modified:
                    request_headers["If-Modified-Since"] = validators.last_modified
            captured = runtime.http.fetch(
                self._request(canonical, request_headers=request_headers or None)
            )
            if captured.status_code == 304:
                if captured.final_url != canonical:
                    raise TerminalJobError("304 redirect changed the source evidence identity")
                self._repository.record_not_modified(
                    run_id=job.run_id,
                    canonical_url=canonical,
                    candidate_id=payload.candidate_id,
                )
                return

            html = _decode_html(captured.body, captured.headers.get("content-type"))
            document = self._extract_document(html)
            if len(
                document.normalized_text
            ) < _MIN_BROWSER_FALLBACK_TEXT_CHARS and adapter.browser_fallback_allowed(canonical):
                captured = runtime.browser.fetch(self._request(canonical))
                html = _decode_html(captured.body, captured.headers.get("content-type"))
                document = self._extract_document(html)
            if not document.normalized_text:
                raise TerminalJobError("captured page contained no reviewable visible text")

            evidence_title = (
                candidate.title
                if candidate is not None and document.title == "Untitled official page"
                else document.title
            )
            adapted = adapter.adapt(captured.final_url, title=evidence_title)
            if candidate is not None and adapted.canonical_url != candidate.canonical_url:
                raise TerminalJobError("selected candidate redirected to a different evidence page")
            normalized_bytes = document.normalized_text.encode("utf-8")
            raw_object = self._storage.put(
                BytesIO(captured.body),
                media_type=captured.headers.get("content-type", "text/html"),
                max_bytes=self._html_max_bytes,
            )
            normalized_object = self._storage.put(
                BytesIO(normalized_bytes),
                media_type="text/plain; charset=utf-8",
                max_bytes=self._html_max_bytes,
            )
            images, image_failures = self._capture_images(
                runtime,
                page_url=captured.final_url,
                document=document,
            )
            image_fingerprints = "\0".join(image.stored_object.digest.value for image in images)
            fingerprint = hashlib.sha256(
                f"{PARSER_VERSION}\0{normalized_object.digest.value}\0{image_fingerprints}".encode()
            ).hexdigest()
            published_at = (
                candidate.published_at
                if candidate is not None
                else _published_at(document.metadata)
            )
            self._repository.persist_capture(
                run_id=job.run_id,
                candidate_id=payload.candidate_id,
                capture=PreparedCapture(
                    source=adapted,
                    title=evidence_title,
                    published_at=published_at,
                    fetched_at=datetime.now(UTC),
                    capture_method=captured.method,
                    http_status=captured.status_code,
                    etag=captured.headers.get("etag"),
                    last_modified=captured.headers.get("last-modified"),
                    raw_object=raw_object,
                    normalized_object=normalized_object,
                    images=images,
                    image_candidate_count=min(len(document.images), self._max_images),
                    image_failure_count=image_failures,
                    evidence_fingerprint_sha256=fingerprint,
                    parser_version=PARSER_VERSION,
                    capture_policy_version=CAPTURE_POLICY_VERSION,
                    document_language=document.document_language,
                ),
            )
        except Exception as error:
            _raise_job_error(error)

    def _capture_images(
        self,
        runtime: CaptureRuntime,
        *,
        page_url: str,
        document: EvidenceDocument,
    ) -> tuple[tuple[PreparedImage, ...], int]:
        captured_images: list[PreparedImage] = []
        failures = 0
        for candidate in document.images[: self._max_images]:
            image_url = urljoin(page_url, candidate.url)
            try:
                runtime.robots.ensure_allowed(image_url)
                image = runtime.http.fetch(
                    CaptureRequest(
                        url=image_url,
                        max_bytes=self._image_max_bytes,
                        timeout_seconds=self._timeout,
                        max_redirects=self._max_redirects,
                        accepted_media_types=(
                            "image/gif",
                            "image/jpeg",
                            "image/png",
                            "image/webp",
                        ),
                        purpose=CapturePurpose.ASSET,
                    )
                )
                media_type = image.headers.get("content-type", "").partition(";")[0].lower()
                if not _matches_image_signature(image.body, media_type):
                    failures += 1
                    continue
                stored = self._storage.put(
                    BytesIO(image.body),
                    media_type=media_type,
                    max_bytes=self._image_max_bytes,
                )
                captured_images.append(
                    PreparedImage(
                        original_url=image.final_url,
                        alt_text=candidate.alt_text,
                        stored_object=stored,
                    )
                )
            except SourceAccessError:
                failures += 1
        return tuple(captured_images), failures

    def _adapter_for(self, url: str) -> SiteAdapter:
        matches = [adapter for adapter in self._adapters if adapter.supports(url)]
        if len(matches) != 1:
            raise TerminalJobError("URL does not match exactly one approved site adapter")
        return matches[0]

    def _request(
        self,
        url: str,
        *,
        request_headers: Mapping[str, str] | None = None,
    ) -> CaptureRequest:
        return CaptureRequest(
            url=url,
            max_bytes=self._html_max_bytes,
            timeout_seconds=self._timeout,
            max_redirects=self._max_redirects,
            request_headers=request_headers,
        )


@dataclass(frozen=True, slots=True)
class _DiscoverPayload:
    urls: tuple[str, ...]
    limit: int
    source_types: frozenset[SourceType]
    published_from: datetime | None
    published_to: datetime | None


@dataclass(frozen=True, slots=True)
class _CapturePayload:
    url: str | None
    candidate_id: UUID | None


def _discover_payload(
    payload: Mapping[str, Any],
    quick_limit: int,
    targeted_limit: int,
) -> _DiscoverPayload:
    raw_urls = payload.get("listing_urls")
    if not isinstance(raw_urls, list) or not raw_urls or len(raw_urls) > _MAX_LISTING_URLS:
        raise TerminalJobError("listing_urls must contain between 1 and 10 URLs")
    if not all(isinstance(url, str) and url for url in raw_urls):
        raise TerminalJobError("every discovery URL must be a non-empty string")
    mode = payload.get("mode", "quick")
    if mode not in {"quick", "targeted"}:
        raise TerminalJobError("discovery mode must be quick or targeted")
    if mode == "quick" and len(raw_urls) != 1:
        raise TerminalJobError("quick discovery accepts exactly one listing URL")
    maximum = quick_limit if mode == "quick" else targeted_limit
    limit = payload.get("candidate_limit", maximum)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= maximum:
        raise TerminalJobError(f"candidate_limit must be between 1 and {maximum}")
    raw_types = payload.get("source_types", [])
    if not isinstance(raw_types, list):
        raise TerminalJobError("source_types must be a list")
    try:
        source_types = frozenset(SourceType(item) for item in raw_types)
    except (ValueError, TypeError) as error:
        raise TerminalJobError("source_types contains an unsupported value") from error
    return _DiscoverPayload(
        urls=tuple(dict.fromkeys(raw_urls)),
        limit=limit,
        source_types=source_types,
        published_from=_optional_datetime(payload.get("published_from")),
        published_to=_optional_datetime(payload.get("published_to")),
    )


def _capture_payload(payload: Mapping[str, Any]) -> _CapturePayload:
    url = payload.get("url")
    if url is not None and (not isinstance(url, str) or not url):
        raise TerminalJobError("capture URL must be a non-empty string")
    raw_candidate_id = payload.get("candidate_id")
    try:
        candidate_id = UUID(raw_candidate_id) if raw_candidate_id is not None else None
    except (ValueError, TypeError, AttributeError) as error:
        raise TerminalJobError("candidate_id must be a UUID") from error
    if (url is None) == (candidate_id is None):
        raise TerminalJobError("provide exactly one of url or candidate_id")
    return _CapturePayload(url=url, candidate_id=candidate_id)


def _matches_filters(candidate: DiscoveredPage, payload: _DiscoverPayload) -> bool:
    if payload.source_types and candidate.source_type not in payload.source_types:
        return False
    if payload.published_from is not None and (
        candidate.published_at is None or candidate.published_at < payload.published_from
    ):
        return False
    return not (
        payload.published_to is not None
        and (candidate.published_at is None or candidate.published_at > payload.published_to)
    )


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TerminalJobError("date filters must be ISO-8601 strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TerminalJobError("date filters must be valid ISO-8601 values") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _published_at(metadata: Mapping[str, str]) -> datetime | None:
    for key in ("article:published_time", "date", "datepublished"):
        value = metadata.get(key)
        if value:
            try:
                return _optional_datetime(value)
            except TerminalJobError:
                continue
    return None


def _decode_html(body: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        for parameter in content_type.split(";")[1:]:
            key, separator, value = parameter.strip().partition("=")
            if separator and key.lower() == "charset":
                charset = value.strip("\"'")
    try:
        return body.decode(charset, errors="replace")
    except LookupError as error:
        raise TerminalJobError("official page declared an unknown text encoding") from error


def _matches_image_signature(body: bytes, media_type: str) -> bool:
    signatures = {
        "image/gif": (b"GIF87a", b"GIF89a"),
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/webp": (b"RIFF",),
    }
    allowed = signatures.get(media_type)
    if allowed is None or not any(body.startswith(prefix) for prefix in allowed):
        return False
    return media_type != "image/webp" or len(body) >= 12 and body[8:12] == b"WEBP"


def _raise_job_error(error: Exception) -> None:
    if isinstance(error, (RetryableJobError, TerminalJobError)):
        raise error
    if isinstance(error, UpstreamStatusError):
        if error.status_code in {408, 425, 429} or error.status_code >= 500:
            raise RetryableJobError(str(error)) from error
        raise TerminalJobError(str(error)) from error
    if isinstance(
        error,
        (
            BrowserUnavailableError,
            ResponseTooLargeError,
            RobotsDeniedError,
            SourceStateError,
            UnsupportedMediaTypeError,
            ValueError,
        ),
    ):
        raise TerminalJobError(str(error)) from error
    if isinstance(error, CaptureError):
        raise RetryableJobError(str(error)) from error
    if isinstance(error, SourceAccessError):
        raise TerminalJobError(str(error)) from error
    raise error
