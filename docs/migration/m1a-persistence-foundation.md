# M1-A durable persistence foundation

## Implemented

- PostgreSQL 17 with pgvector 0.8.2 through Docker Compose;
- Alembic migration `20260728_0001`;
- project, ingestion-run, leased-job, and append-only audit-event records;
- pure Python run-transition rules independent from SQLAlchemy and FastAPI;
- database-backed job claims, bounded retries, terminal `needs_attention`, and idempotent run
  creation;
- separate worker delivery entrypoint;
- liveness (`/health`) and dependency readiness (`/ready`) endpoints;
- SQLite transaction tests for fast local feedback and PostgreSQL migration/queue tests in CI.

## Deliberately not implemented

M1-A does not discover or fetch websites, parse documents, call a model, create claims, resolve
conflicts, or publish knowledge snapshots. Those capabilities belong to M1-B and M1-C.

## Local verification

```powershell
.\scripts\setup.ps1
.\scripts\database.ps1 up
$env:GAMECRAFTER_TEST_DATABASE_URL = "postgresql+psycopg://gamecrafter:gamecrafter_local@127.0.0.1:5432/gamecrafter"
.\scripts\verify.ps1
```

Without Docker, fast tests run and the PostgreSQL test is explicitly reported as skipped. GitHub
Actions always starts the pinned pgvector image, applies the migration, and runs the PostgreSQL
test.
