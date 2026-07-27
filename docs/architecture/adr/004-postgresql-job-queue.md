# ADR-004: PostgreSQL-backed durable worker queue

Status: accepted for M1-A.

## Context

Source capture and later model calls can outlive one HTTP request. The local first release needs
resumable work, bounded retries, idempotency, and visible terminal failures without adding Redis or
a distributed-service platform prematurely.

## Decision

Store ingestion runs and jobs in PostgreSQL. A separate Python worker claims jobs with
`FOR UPDATE SKIP LOCKED`, uses an expiring lease, and commits job state, run state, and audit events
in one transaction. Retries are bounded and delayed; permanent or exhausted failures enter
`needs_attention`.

The application depends on a `JobQueue` port. PostgreSQL is the first adapter, so a later queue
replacement does not change domain state rules or worker handlers.

## Consequences

- an API restart does not erase queued work;
- expired leases can be reclaimed after worker failure;
- idempotency keys prevent duplicate runs and charges;
- PostgreSQL is required for the real concurrency semantics;
- CI must execute migrations and queue tests against PostgreSQL;
- Redis, Celery, and a second operational datastore are deferred until measured load justifies them.
