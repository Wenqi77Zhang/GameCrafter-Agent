"""In-process host and global access scheduling for controlled source requests."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from urllib.parse import urlsplit


class HostAccessScheduler:
    """Apply per-host concurrency, global concurrency, and minimum spacing."""

    def __init__(
        self,
        *,
        global_concurrency: int,
        per_host_concurrency: int,
        min_interval_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if global_concurrency <= 0 or per_host_concurrency <= 0:
            raise ValueError("scheduler concurrency must be positive")
        if min_interval_seconds < 0:
            raise ValueError("scheduler interval cannot be negative")
        self._global = BoundedSemaphore(global_concurrency)
        self._per_host_concurrency = per_host_concurrency
        self._default_interval = min_interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._state_lock = Lock()
        self._host_semaphores: dict[str, BoundedSemaphore] = {}
        self._host_intervals: dict[str, float] = {}
        self._next_allowed: dict[str, float] = {}

    @contextmanager
    def slot(self, url: str) -> Iterator[None]:
        hostname = urlsplit(url).hostname
        if hostname is None:
            raise ValueError("scheduled URL must include a hostname")
        with self._state_lock:
            host_semaphore = self._host_semaphores.setdefault(
                hostname,
                BoundedSemaphore(self._per_host_concurrency),
            )
        self._global.acquire()
        host_semaphore.acquire()
        try:
            with self._state_lock:
                now = self._monotonic()
                scheduled_at = max(now, self._next_allowed.get(hostname, now))
                interval = self._host_intervals.get(hostname, self._default_interval)
                self._next_allowed[hostname] = scheduled_at + interval
            delay = scheduled_at - self._monotonic()
            if delay > 0:
                self._sleep(delay)
            yield
        finally:
            host_semaphore.release()
            self._global.release()

    def update_host_interval(self, hostname: str, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("host interval cannot be negative")
        with self._state_lock:
            current = self._host_intervals.get(hostname, self._default_interval)
            self._host_intervals[hostname] = max(current, seconds)
