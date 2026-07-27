"""Run the database-backed GameCrafter worker."""

from __future__ import annotations

import argparse
import time

from gamecrafter.application.jobs import Worker
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.job_queue import DatabaseJobQueue
from gamecrafter.infrastructure.database.session import get_session_factory


def create_worker() -> Worker:
    """Build the worker shell; feature handlers arrive in M1-B and M1-C."""

    settings = get_settings()
    return Worker(
        queue=DatabaseJobQueue(get_session_factory()),
        handlers={},
        worker_id=settings.worker_id,
        lease_seconds=settings.job_lease_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GameCrafter background worker.")
    parser.add_argument("--once", action="store_true", help="Poll once and exit.")
    args = parser.parse_args()
    settings = get_settings()
    worker = create_worker()

    while True:
        worked = worker.run_once()
        if args.once:
            return 0
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
