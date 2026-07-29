"""Explicitly allowed Playwright fallback for JavaScript-rendered official pages."""

from __future__ import annotations

from gamecrafter.application.ports.source_capture import CapturedPage, CaptureRequest
from gamecrafter.domain.knowledge.sources import CaptureMethod
from gamecrafter.infrastructure.ingestion.http import (
    CaptureError,
    RedirectLimitError,
    ResponseTooLargeError,
    UnsupportedMediaTypeError,
    UpstreamStatusError,
)
from gamecrafter.infrastructure.ingestion.robots import GAMECRAFTER_USER_AGENT
from gamecrafter.security.source_policy import (
    AccessBudget,
    AccessPurpose,
    OfficialSourcePolicy,
    SourcePolicyError,
)


class BrowserUnavailableError(CaptureError):
    """Raised when Playwright or its Chromium runtime is unavailable."""


class BrowserPageFetcher:
    """Render only adapter-approved pages inside an isolated browser context."""

    def __init__(
        self,
        *,
        policy: OfficialSourcePolicy,
        budget: AccessBudget,
    ) -> None:
        self._policy = policy
        self._budget = budget

    def fetch(self, request: CaptureRequest) -> CapturedPage:
        if not self._policy.browser_fallback_allowed(request.url):
            raise SourcePolicyError("browser fallback is not allowed for this page")
        authorized = self._policy.authorize(request.url, purpose=AccessPurpose.PAGE)
        self._budget.consume()
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise BrowserUnavailableError("Playwright is not installed") from error

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        accept_downloads=False,
                        ignore_https_errors=False,
                        java_script_enabled=True,
                        service_workers="block",
                        user_agent=f"{GAMECRAFTER_USER_AGENT}/0.1",
                    )
                    try:
                        return self._capture_in_context(
                            context,
                            request=request,
                            requested_url=authorized.url,
                        )
                    finally:
                        context.close()
                finally:
                    browser.close()
        except PlaywrightError as error:
            raise BrowserUnavailableError(
                "controlled browser capture failed to start or run"
            ) from error

    def _capture_in_context(self, context, *, request: CaptureRequest, requested_url: str):
        document_requests = 0
        subresource_requests = 0
        subresource_limit_exceeded = False

        def route_request(route) -> None:
            nonlocal document_requests, subresource_limit_exceeded, subresource_requests
            outbound = route.request
            purpose = (
                AccessPurpose.PAGE if outbound.resource_type == "document" else AccessPurpose.ASSET
            )
            try:
                self._policy.authorize(
                    outbound.url,
                    purpose=purpose,
                    resolve_dns=True,
                )
            except SourcePolicyError:
                route.abort("blockedbyclient")
                return
            if purpose is AccessPurpose.PAGE:
                document_requests += 1
                if document_requests > request.max_redirects + 1:
                    route.abort("blockedbyclient")
                    return
            else:
                subresource_requests += 1
                if subresource_requests > request.max_subresources:
                    subresource_limit_exceeded = True
                    route.abort("blockedbyclient")
                    return
            route.continue_()

        page = context.new_page()
        page.set_default_timeout(request.timeout_seconds * 1000)
        page.route("**/*", route_request)
        page.on("dialog", lambda dialog: dialog.dismiss())
        page.on("popup", lambda popup: popup.close())
        response = page.goto(
            requested_url,
            wait_until="domcontentloaded",
            timeout=request.timeout_seconds * 1000,
        )
        if document_requests > request.max_redirects + 1:
            raise RedirectLimitError("official source redirect limit was exceeded")
        if subresource_limit_exceeded:
            raise CaptureError("controlled browser subresource limit was exceeded")
        if response is None:
            raise CaptureError("controlled browser returned no document response")
        if response.status < 200 or response.status >= 300:
            raise UpstreamStatusError(response.status)
        content_type = response.headers.get("content-type")
        media_type = content_type.partition(";")[0].strip().lower() if content_type else ""
        accepted_media_types = {item.lower() for item in request.accepted_media_types}
        if media_type not in accepted_media_types:
            raise UnsupportedMediaTypeError(
                f"official source returned unsupported type {media_type or 'missing'}"
            )
        if request.ready_selector:
            page.locator(request.ready_selector).first.wait_for(state="attached")
        final_url = self._policy.authorize(
            page.url,
            purpose=AccessPurpose.PAGE,
        ).url
        body = page.content().encode("utf-8")
        if len(body) > request.max_bytes:
            raise ResponseTooLargeError("rendered page exceeded the response byte limit")
        return CapturedPage(
            requested_url=requested_url,
            final_url=final_url,
            status_code=response.status,
            headers={
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in {"content-type", "etag", "last-modified"}
            },
            body=body,
            method=CaptureMethod.PLAYWRIGHT,
        )
