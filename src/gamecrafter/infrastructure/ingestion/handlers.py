"""Composition helpers for B3 source-ingestion worker handlers."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.application.jobs import JobHandler
from gamecrafter.application.source_ingestion import (
    CAPTURE_SOURCE_TASK,
    DISCOVER_SOURCE_TASK,
    CaptureRuntime,
    SourceIngestionHandlers,
)
from gamecrafter.config.settings import Settings
from gamecrafter.infrastructure.database.source_repository import DatabaseSourceRepository
from gamecrafter.infrastructure.ingestion.browser import BrowserPageFetcher
from gamecrafter.infrastructure.ingestion.html import extract_evidence_document
from gamecrafter.infrastructure.ingestion.http import HttpPageFetcher
from gamecrafter.infrastructure.ingestion.nte import NTE_ACCESS_RULES, NTE_SITE_ADAPTERS
from gamecrafter.infrastructure.ingestion.robots import RobotsGuard
from gamecrafter.infrastructure.ingestion.scheduler import HostAccessScheduler
from gamecrafter.infrastructure.storage.local import LocalObjectStorage
from gamecrafter.security.source_policy import AccessBudget, OfficialSourcePolicy


def build_source_handlers(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> Mapping[str, JobHandler]:
    """Build source handlers with a fresh request budget for every durable job."""

    repository = DatabaseSourceRepository(
        session_factory,
        actor_id=settings.worker_id,
    )
    object_storage = LocalObjectStorage(settings.object_storage_path)

    def runtime_factory(max_requests: int) -> CaptureRuntime:
        scheduler = HostAccessScheduler(
            global_concurrency=settings.source_global_max_concurrency,
            per_host_concurrency=settings.source_max_concurrency_per_host,
            min_interval_seconds=settings.source_min_interval_seconds,
        )
        budget = AccessBudget(
            max_requests=max_requests,
            max_redirects_per_request=settings.source_max_redirects,
            max_concurrency_per_host=settings.source_max_concurrency_per_host,
            min_interval_seconds=settings.source_min_interval_seconds,
        )
        policy = OfficialSourcePolicy(NTE_ACCESS_RULES)
        http = HttpPageFetcher(
            policy=policy,
            budget=budget,
            scheduler=scheduler,
        )
        return CaptureRuntime(
            http=http,
            browser=BrowserPageFetcher(
                policy=policy,
                budget=budget,
                scheduler=scheduler,
            ),
            robots=RobotsGuard(
                fetcher=http,
                scheduler=scheduler,
                timeout_seconds=settings.source_timeout_seconds,
            ),
        )

    handlers = SourceIngestionHandlers(
        adapters=NTE_SITE_ADAPTERS,
        repository=repository,
        object_storage=object_storage,
        runtime_factory=runtime_factory,
        evidence_extractor=extract_evidence_document,
        timeout_seconds=settings.source_timeout_seconds,
        html_max_bytes=settings.source_html_max_bytes,
        image_max_bytes=settings.source_image_max_bytes,
        max_images_per_page=settings.source_max_images_per_page,
        max_redirects=settings.source_max_redirects,
        quick_candidate_limit=settings.source_quick_candidate_limit,
        targeted_candidate_limit=settings.source_targeted_candidate_limit,
    )
    return {
        DISCOVER_SOURCE_TASK: handlers.discover,
        CAPTURE_SOURCE_TASK: handlers.capture,
    }
