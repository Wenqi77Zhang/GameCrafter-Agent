# M1-C C2.5 NTE PostgreSQL acceptance

## Outcome

C2.5 adds a repeatable acceptance gate for the first NTE Knowledge slice. It takes the committed,
source-attributed public English homepage snapshot, binds it to a unique immutable source version
and the server-owned game entity key, enqueues `knowledge.extract`, executes the real PostgreSQL
leased worker, and inspects the durable result.

This is reviewed snapshot acceptance, not a claim that the current live NTE site was captured on
the test date. It performs no model network call and reports zero input, output, and total tokens.

## Acceptance gates

- the database is migrated through Alembic head and uses real PostgreSQL constraints;
- the same idempotency key and payload return one run and one job;
- the leased worker reaches `succeeded` through the registered extraction handler;
- one exact replay invocation records the reviewed fixture ID and zero token usage;
- two candidate Claims and two exact evidence spans commit with the immutable result marker;
- completion includes both `knowledge.extraction_persisted` and `job.completed` audit events;
- every returned quote exists in the normalized public snapshot and points to the exact source
  version and official URL;
- result reads contain hashes, counts, versions, usage, and redacted invocation metadata, but no
  source body or local object key.

## Safe local execution

`scripts/acceptance.ps1` requires `GAMECRAFTER_TEST_DATABASE_URL` or an explicit `-DatabaseUrl`.
Before migration, it rejects non-localhost hosts and database names that do not contain `test` or
`acceptance`. This prevents an accidental acceptance run against a personal or production database.
The URL is held in process environment only and is never printed by the script.

The test creates uniquely named acceptance records and leaves them auditable. Use a disposable
database; do not expect the test to erase history after success.

## Verification boundary

GitHub CI supplies `gamecrafter_test`, runs every migration, and executes this acceptance with the
rest of the PostgreSQL suite. Local validation also passed against an isolated `gamecrafter_test`
database. Current live-site capture, deterministic conflict processing, human review, and snapshot
publication remain later gates.
