"""Bounded HTTP-first official-page capture."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

import httpx2

from gamecrafter.application.ports.source_capture import (
    GAMECRAFTER_USER_AGENT,
    CapturedPage,
    CaptureError,
    CapturePurpose,
    CaptureRequest,
    RedirectLimitError,
    RequestScheduler,
    ResponseTooLargeError,
    UnsupportedMediaTypeError,
    UpstreamStatusError,
)
from gamecrafter.domain.knowledge.sources import CaptureMethod
from gamecrafter.security.source_policy import (
    AccessBudget,
    AccessPurpose,
    OfficialSourcePolicy,
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "content-type",
        "etag",
        "last-modified",
    }
)
_CONDITIONAL_REQUEST_HEADERS = frozenset({"if-none-match", "if-modified-since"})


class HttpPageFetcher:
    """Fetch official pages with manual redirect validation and byte limits."""

    def __init__(
        self,
        *,
        policy: OfficialSourcePolicy,
        budget: AccessBudget,
        scheduler: RequestScheduler,
        client_factory: Callable[[], httpx2.Client] | None = None,
    ) -> None:
        self._policy = policy
        self._budget = budget
        self._scheduler = scheduler
        self._client_factory = client_factory or self._default_client

    def fetch(self, request: CaptureRequest) -> CapturedPage:
        purpose = (
            AccessPurpose.ROBOTS
            if request.purpose is CapturePurpose.ROBOTS
            else (
                AccessPurpose.ASSET
                if request.purpose is CapturePurpose.ASSET
                else AccessPurpose.PAGE
            )
        )
        requested_url = self._policy.authorize(
            request.url,
            purpose=purpose,
            resolve_dns=False,
        ).url
        current_url = requested_url
        redirects = 0
        with self._client_factory() as client:
            while True:
                authorized = self._policy.authorize(
                    current_url,
                    purpose=purpose,
                )
                self._budget.consume()
                headers = {"User-Agent": f"{GAMECRAFTER_USER_AGENT}/0.1"}
                for key, value in (request.request_headers or {}).items():
                    if key.lower() not in _CONDITIONAL_REQUEST_HEADERS:
                        raise CaptureError("capture request included a forbidden HTTP header")
                    headers[key] = value
                with (
                    self._scheduler.slot(authorized.url),
                    client.stream(
                        "GET", authorized.url, headers=headers, timeout=request.timeout_seconds
                    ) as response,
                ):
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise UpstreamStatusError(response.status_code)
                        if redirects >= min(
                            request.max_redirects,
                            self._budget.max_redirects_per_request,
                        ):
                            raise RedirectLimitError("official source redirect limit was exceeded")
                        current_url = urljoin(authorized.url, location)
                        redirects += 1
                        client.cookies.clear()
                        continue
                    if response.status_code == 304:
                        return CapturedPage(
                            requested_url=requested_url,
                            final_url=authorized.url,
                            status_code=304,
                            headers=_safe_headers(response.headers),
                            body=b"",
                            method=CaptureMethod.HTTP,
                        )
                    if response.status_code < 200 or response.status_code >= 300:
                        raise UpstreamStatusError(response.status_code)
                    _validate_content_length(response.headers, request.max_bytes)
                    _validate_media_type(response.headers, request.accepted_media_types)
                    body = _read_bounded(response, request.max_bytes)
                    return CapturedPage(
                        requested_url=requested_url,
                        final_url=authorized.url,
                        status_code=response.status_code,
                        headers=_safe_headers(response.headers),
                        body=body,
                        method=CaptureMethod.HTTP,
                    )

    @staticmethod
    def _default_client() -> httpx2.Client:
        return httpx2.Client(
            follow_redirects=False,
            trust_env=False,
            cookies={},
        )


def _safe_headers(headers: httpx2.Headers) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in _SAFE_RESPONSE_HEADERS
    }


def _validate_content_length(headers: httpx2.Headers, max_bytes: int) -> None:
    value = headers.get("content-length")
    if value is None:
        return
    try:
        content_length = int(value)
    except ValueError as error:
        raise CaptureError("official source returned an invalid Content-Length") from error
    if content_length < 0 or content_length > max_bytes:
        raise ResponseTooLargeError("official source exceeded the response byte limit")


def _validate_media_type(headers: httpx2.Headers, accepted: tuple[str, ...]) -> None:
    value = headers.get("content-type")
    if value is None:
        raise UnsupportedMediaTypeError("official source did not declare a media type")
    media_type = value.partition(";")[0].strip().lower()
    if media_type not in {item.lower() for item in accepted}:
        raise UnsupportedMediaTypeError(f"official source returned unsupported type {media_type}")


def _read_bounded(response: httpx2.Response, max_bytes: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLargeError("official source exceeded the response byte limit")
    return bytes(body)
