import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.postgres

LEGACY_REVISION = "20260729_0003"


def migration_config() -> Config:
    test_url = os.getenv("GAMECRAFTER_TEST_DATABASE_URL")
    migration_url = os.getenv("GAMECRAFTER_DATABASE_URL")
    if not test_url or not migration_url:
        pytest.skip("PostgreSQL migration URLs are not configured")
    if test_url != migration_url:
        pytest.skip("Migration preservation test requires the isolated test database")
    return Config(str(Path(__file__).parents[2] / "alembic.ini"))


def test_workflow_rename_preserves_legacy_lineage_across_round_trip() -> None:
    config = migration_config()
    database_url = os.environ["GAMECRAFTER_TEST_DATABASE_URL"]
    project_id = uuid4()
    run_id = uuid4()
    job_id = uuid4()
    audit_id = uuid4()
    entity_id = uuid4()
    claim_id = uuid4()
    slug = f"workflow-migration-{uuid4().hex}"
    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        command.downgrade(config, LEGACY_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO projects
                        (id, slug, name, default_locale, created_at, updated_at)
                    VALUES (:id, :slug, '异环', 'zh-CN', NOW(), NOW())
                    """
                ),
                {"id": project_id, "slug": slug},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ingestion_runs
                        (id, project_id, idempotency_key, status, checkpoint, version,
                         created_at, updated_at, started_at, finished_at)
                    VALUES
                        (:id, :project_id, 'legacy-run', 'succeeded', 'knowledge.extract', 3,
                         NOW(), NOW(), NOW(), NOW())
                    """
                ),
                {"id": run_id, "project_id": project_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs
                        (id, run_id, task_type, status, payload, attempts, max_attempts,
                         available_at, created_at, updated_at)
                    VALUES
                        (:id, :run_id, 'knowledge.extract', 'completed', '{}'::jsonb, 1, 3,
                         NOW(), NOW(), NOW())
                    """
                ),
                {"id": job_id, "run_id": run_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (id, project_id, run_id, event_type, actor_type, actor_id,
                         payload, occurred_at)
                    VALUES
                        (:id, :project_id, :run_id, 'legacy.created', 'system',
                         'migration-test', '{}'::jsonb, NOW())
                    """
                ),
                {"id": audit_id, "project_id": project_id, "run_id": run_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_entities
                        (id, project_id, entity_type, canonical_key, display_name,
                         aliases, details, created_at, updated_at)
                    VALUES
                        (:id, :project_id, 'game', 'nte', '异环', '[]'::jsonb,
                         '{}'::jsonb, NOW(), NOW())
                    """
                ),
                {"id": entity_id, "project_id": project_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_claims
                        (id, project_id, subject_entity_id, extraction_run_id, predicate,
                         value_kind, value, normalized_value, value_fingerprint_sha256,
                         scope_fingerprint_sha256, confidence, locale, region,
                         model_provider, model_name, prompt_version, schema_version, created_at)
                    VALUES
                        (:id, :project_id, :entity_id, :run_id, 'game.name', 'string',
                         '"Neverness to Everness"'::jsonb, 'Neverness to Everness',
                         :value_hash, :scope_hash, 1, 'en', 'global', 'offline',
                         'fixture', 'test-v1', 'claim-v1', NOW())
                    """
                ),
                {
                    "id": claim_id,
                    "project_id": project_id,
                    "entity_id": entity_id,
                    "run_id": run_id,
                    "value_hash": "a" * 64,
                    "scope_hash": "b" * 64,
                },
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            run = connection.execute(
                text("SELECT id, workflow_kind FROM workflow_runs WHERE id = :id"),
                {"id": run_id},
            ).one()
            assert run.id == run_id
            assert run.workflow_kind == "knowledge.extract"
            assert connection.scalar(text("SELECT to_regclass('ingestion_runs')")) is None
            assert (
                connection.scalar(
                    text("SELECT run_id FROM workflow_jobs WHERE id = :id"),
                    {"id": job_id},
                )
                == run_id
            )
            assert (
                connection.scalar(
                    text("SELECT run_id FROM audit_events WHERE id = :id"),
                    {"id": audit_id},
                )
                == run_id
            )
            assert (
                connection.scalar(
                    text("SELECT extraction_run_id FROM knowledge_claims WHERE id = :id"),
                    {"id": claim_id},
                )
                == run_id
            )

        command.downgrade(config, LEGACY_REVISION)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT id FROM ingestion_runs WHERE id = :id"),
                    {"id": run_id},
                )
                == run_id
            )
            assert (
                connection.scalar(
                    text("SELECT run_id FROM ingestion_jobs WHERE id = :id"),
                    {"id": job_id},
                )
                == run_id
            )
            assert (
                connection.scalar(
                    text("SELECT extraction_run_id FROM knowledge_claims WHERE id = :id"),
                    {"id": claim_id},
                )
                == run_id
            )
    finally:
        engine.dispose()
        command.upgrade(config, "head")
