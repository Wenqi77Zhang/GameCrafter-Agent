from importlib.metadata import version

import pytest

from gamecrafter.application.ports.source_capture import CaptureRequest
from gamecrafter.infrastructure.ingestion.browser import BrowserPageFetcher
from gamecrafter.infrastructure.ingestion.nte import NTE_ACCESS_RULES
from gamecrafter.security.source_policy import (
    AccessBudget,
    OfficialSourcePolicy,
    SourcePolicyError,
)


class PublicResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        return ("8.8.8.8",)


def test_playwright_python_runtime_is_an_explicit_project_dependency() -> None:
    major, minor, *_ = (int(part) for part in version("playwright").split("."))

    assert (major, minor) >= (1, 61)


def test_browser_fetcher_refuses_pages_without_adapter_permission() -> None:
    fetcher = BrowserPageFetcher(
        policy=OfficialSourcePolicy(NTE_ACCESS_RULES, resolver=PublicResolver()),
        budget=AccessBudget(max_requests=1),
    )

    with pytest.raises(SourcePolicyError, match="not allowed"):
        fetcher.fetch(
            CaptureRequest(
                url="https://nte.perfectworld.com/en/article/news/index.html",
                max_bytes=1024,
                timeout_seconds=1,
                max_redirects=1,
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("max_bytes", 0, "max_bytes"),
        ("timeout_seconds", 0, "timeout_seconds"),
        ("max_redirects", -1, "max_redirects"),
        ("max_subresources", -1, "max_subresources"),
    ],
)
def test_capture_request_rejects_invalid_resource_budgets(
    field: str,
    value: int,
    message: str,
) -> None:
    values = {
        "url": "https://nte.perfectworld.com/en/main.html",
        "max_bytes": 1024,
        "timeout_seconds": 1,
        "max_redirects": 1,
        "max_subresources": 100,
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        CaptureRequest(**values)
