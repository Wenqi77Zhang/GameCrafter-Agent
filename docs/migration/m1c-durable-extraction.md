# M1-C C2.3b durable zero-cost extraction

## Outcome

C2.3b closes the backend path from an explicit extraction command to durable, reviewable candidate
claims. It registers `knowledge.extract` on the existing PostgreSQL worker and does not introduce a
second queue, broker, autonomous agent conversation, or paid model path.

The delivery surface now provides:

- `POST /api/projects/{project_id}/knowledge-extractions` with strict idempotency;
- `GET /api/projects/{project_id}/knowledge-extractions/{run_id}` for redacted result traces;
- `GET /api/projects/{project_id}/knowledge-claims` for candidate claims and exact evidence;
- disabled-by-default preflight and exact local replay as the only runnable C2 provider modes.

## Durable execution and atomicity

The worker validates that the run kind, project, source version, normalized-text asset, and subject
agree. It then reads the content-addressed object with a configured byte limit and verifies exact
size, SHA-256, UTF-8 decoding, and nonblank text before the Harness runs.

`model_invocations` records one lifecycle row per job attempt and deterministic chunk. A row stores
only operational metadata: request and chunk hashes, offsets, status, provider/model/response IDs,
usage, count, timestamps, and a safe error class. Source, prompt, and model-response bodies are not
stored there.

On whole-document success, candidate claims, exact evidence spans,
`knowledge_extraction_results`, and `knowledge.extraction_persisted` commit in one database
transaction. The result row is immutable and is the retry idempotency marker. If it already exists,
the handler exits without producing duplicate claims or invocations.

## Database and trust boundaries

Alembic revision `20260803_0005` adds the result and invocation tables, indexes, status/usage/hash
constraints, restrictive foreign keys, an immutable-result trigger, and lineage triggers that keep
the run kind, project, source, and subject aligned. API reads are project-scoped and expose no raw
source object or local object path.

External source and replay data remain untrusted. The fixture loader verifies its schema, source
digest, request fingerprint, exact evidence, and provenance notice. API preflight additionally
requires that the configured fixture exactly matches the selected immutable source and covers every
chunk fingerprint. Missing or approximate replay is rejected; there is no network or paid fallback.

## Verification

- unit and API tests cover disabled mode, exact replay preflight, strict settings, and OpenAPI paths;
- SQLite integration tests cover successful worker execution, exact evidence persistence,
  redacted traces, terminal replay failure, and idempotent retry;
- PostgreSQL tests and migration round trips exercise the real schema, triggers, queue, and lineage;
- Python lint/format, full non-PostgreSQL tests, frontend checks, and production build remain in the
  repository verification gate.

## Deliberately deferred to C2.4 and later

- the Simplified-Chinese-default, English-switchable extraction interface;
- live NTE capture acceptance against PostgreSQL;
- deterministic conflict processing, human review actions, and snapshot publication;
- embeddings, live provider execution, trend ingestion, and marketing generation.
