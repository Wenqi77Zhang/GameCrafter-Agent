# M1-B source evidence contracts

Status: B1 implemented and locally verified on 2026-07-29.

## Implemented in B1

- framework-independent enums for the nine confirmed source types, candidate states, capture
  methods, change kinds, and evidence-asset roles;
- validated SHA-256 evidence digests;
- project-scoped canonical sources and multilingual content families;
- immutable meaningful source versions with parser and capture-policy versions;
- content-addressed stored-object metadata and version-to-object evidence links;
- reviewable discovery candidates attached to durable ingestion runs;
- PostgreSQL constraints, indexes, and update-prevention triggers for captured evidence;
- a vendor-neutral `ObjectStorage` application port;
- a private local filesystem adapter with streaming hashes, atomic publication, byte limits,
  deduplication, and path-traversal rejection;
- Alembic upgrade and downgrade coverage in CI.

## Data ownership and deletion

PostgreSQL owns relationships, provenance, lifecycle state, and audit references. The configured
object store owns large bytes. A stored object may be physically deleted only after application
logic proves that no `source_assets` row references it. Sources may later be archived without
mutating evidence. Permanent deletion is an explicit workflow and is not implemented in B1.

## Immutability boundary

`stored_objects`, `source_versions`, and `source_assets` reject SQL `UPDATE` operations in
PostgreSQL. A meaningful website change therefore creates another `source_versions` row instead of
rewriting history. Explicit permanent deletion remains possible through a later dependency-aware
application command.

## Deliberately not implemented in B1

B1 does not access a website, normalize URLs, classify real pages, render JavaScript, capture
assets, expose source APIs, stream run events, or provide the Sources and Runs user interfaces.
Those capabilities are implemented in B2 through B4 and must not be claimed yet.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade 20260728_0001
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:GAMECRAFTER_TEST_DATABASE_URL = "postgresql+psycopg://gamecrafter:gamecrafter_local@127.0.0.1:5432/gamecrafter"
.\scripts\verify.ps1
```

The database password shown above is the disposable local Compose default. Shared or deployed
environments must use a different secret.
