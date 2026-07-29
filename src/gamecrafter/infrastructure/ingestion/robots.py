"""robots.txt interpretation isolated from outbound fetching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from gamecrafter.application.ports.source_capture import (
    GAMECRAFTER_USER_AGENT,
    CapturePurpose,
    CaptureRequest,
    PageFetcher,
    RequestScheduler,
    RobotsDeniedError,
    UpstreamStatusError,
)


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """Parsed rules for one already-authorized official origin."""

    origin: str
    text: str

    def can_fetch(self, url: str, *, user_agent: str = GAMECRAFTER_USER_AGENT) -> bool:
        """Return the standard-library parser's decision for one same-origin URL."""

        parsed_origin = urlsplit(self.origin)
        parsed_url = urlsplit(url)
        if (parsed_url.scheme, parsed_url.netloc) != (
            parsed_origin.scheme,
            parsed_origin.netloc,
        ):
            return False
        parser = RobotFileParser()
        parser.set_url(f"{self.origin.rstrip('/')}/robots.txt")
        parser.parse(self.text.splitlines())
        return parser.can_fetch(user_agent, url)

    def crawl_delay(self, *, user_agent: str = GAMECRAFTER_USER_AGENT) -> float | None:
        """Return a valid crawl delay declared for this user agent."""

        parser = RobotFileParser()
        parser.set_url(f"{self.origin.rstrip('/')}/robots.txt")
        parser.parse(self.text.splitlines())
        delay = parser.crawl_delay(user_agent)
        return float(delay) if delay is not None and delay >= 0 else None


@dataclass(frozen=True, slots=True)
class _CachedRules:
    rules: RobotsRules
    expires_at: datetime


class RobotsGuard:
    """Fetch, cache, and conservatively enforce robots rules before page access."""

    def __init__(
        self,
        *,
        fetcher: PageFetcher,
        scheduler: RequestScheduler,
        timeout_seconds: float,
        cache_seconds: int = 3600,
        max_bytes: int = 512 * 1024,
    ) -> None:
        self._fetcher = fetcher
        self._scheduler = scheduler
        self._timeout_seconds = timeout_seconds
        self._cache_seconds = cache_seconds
        self._max_bytes = max_bytes
        self._cache: dict[str, _CachedRules] = {}
        self._lock = Lock()

    def ensure_allowed(self, url: str) -> RobotsRules:
        """Raise when robots disallows the page; allow missing robots files."""

        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        rules = self._cached(origin)
        if rules is None:
            rules = self._fetch(origin)
            with self._lock:
                self._cache[origin] = _CachedRules(
                    rules=rules,
                    expires_at=datetime.now(UTC) + timedelta(seconds=self._cache_seconds),
                )
        delay = rules.crawl_delay()
        if delay is not None:
            self._scheduler.update_host_interval(parsed.hostname or "", delay)
        if not rules.can_fetch(url):
            raise RobotsDeniedError("official source robots rules deny this page")
        return rules

    def _cached(self, origin: str) -> RobotsRules | None:
        now = datetime.now(UTC)
        with self._lock:
            cached = self._cache.get(origin)
            if cached is not None and cached.expires_at > now:
                return cached.rules
            self._cache.pop(origin, None)
        return None

    def _fetch(self, origin: str) -> RobotsRules:
        robots_url = f"{origin}/robots.txt"
        try:
            captured = self._fetcher.fetch(
                CaptureRequest(
                    url=robots_url,
                    max_bytes=self._max_bytes,
                    timeout_seconds=self._timeout_seconds,
                    max_redirects=2,
                    accepted_media_types=("text/plain", "text/html"),
                    purpose=CapturePurpose.ROBOTS,
                )
            )
        except UpstreamStatusError as error:
            if error.status_code in {404, 410}:
                return RobotsRules(origin=origin, text="")
            if error.status_code in {401, 403}:
                return RobotsRules(origin=origin, text="User-agent: *\nDisallow: /")
            raise
        return RobotsRules(
            origin=origin,
            text=captured.body.decode("utf-8", errors="replace"),
        )
