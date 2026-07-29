from contextlib import nullcontext

import pytest

from gamecrafter.application.ports.source_capture import (
    CapturedPage,
    RobotsDeniedError,
    UpstreamStatusError,
)
from gamecrafter.domain.knowledge.sources import CaptureMethod
from gamecrafter.infrastructure.ingestion.robots import RobotsGuard, RobotsRules


def test_robots_rules_apply_only_to_the_same_origin() -> None:
    rules = RobotsRules(
        origin="https://nte.perfectworld.com",
        text="User-agent: GameCrafter\nDisallow: /en/private/\nAllow: /en/\n",
    )

    assert rules.can_fetch("https://nte.perfectworld.com/en/main.html")
    assert not rules.can_fetch("https://nte.perfectworld.com/en/private/secret.html")
    assert not rules.can_fetch("https://evil.example/en/main.html")


class RobotsFetcher:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def fetch(self, request):
        self.calls += 1
        return CapturedPage(
            requested_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "text/plain"},
            body=self.text.encode(),
            method=CaptureMethod.HTTP,
        )


class RecordingScheduler:
    def __init__(self) -> None:
        self.intervals: list[tuple[str, float]] = []

    def slot(self, url: str):
        return nullcontext()

    def update_host_interval(self, hostname: str, seconds: float) -> None:
        self.intervals.append((hostname, seconds))


class FailingRobotsFetcher:
    def __init__(self, status: int) -> None:
        self.status = status

    def fetch(self, request):
        raise UpstreamStatusError(self.status)


def test_robots_guard_caches_rules_and_applies_crawl_delay() -> None:
    fetcher = RobotsFetcher("User-agent: GameCrafter\nCrawl-delay: 3\nDisallow: /private")
    scheduler = RecordingScheduler()
    guard = RobotsGuard(
        fetcher=fetcher,
        scheduler=scheduler,
        timeout_seconds=1,
    )
    public = "https://nte.perfectworld.com/en/main.html"

    guard.ensure_allowed(public)
    guard.ensure_allowed(public)

    assert fetcher.calls == 1
    assert scheduler.intervals == [
        ("nte.perfectworld.com", 3.0),
        ("nte.perfectworld.com", 3.0),
    ]
    with pytest.raises(RobotsDeniedError):
        guard.ensure_allowed("https://nte.perfectworld.com/private")


def test_missing_robots_allows_but_forbidden_robots_denies() -> None:
    scheduler = RecordingScheduler()
    page_url = "https://nte.perfectworld.com/en/main.html"
    missing = RobotsGuard(
        fetcher=FailingRobotsFetcher(404),
        scheduler=scheduler,
        timeout_seconds=1,
    )
    forbidden = RobotsGuard(
        fetcher=FailingRobotsFetcher(403),
        scheduler=scheduler,
        timeout_seconds=1,
    )

    assert missing.ensure_allowed(page_url).can_fetch(page_url)
    with pytest.raises(RobotsDeniedError):
        forbidden.ensure_allowed(page_url)
