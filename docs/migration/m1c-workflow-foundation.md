# M1-C C2.3a generic workflow foundation

## Outcome

C2.3a generalizes the durable execution layer created for source ingestion so knowledge and later
marketing workflows can reuse it. It does not implement durable knowledge extraction itself.

- `ingestion_runs` is renamed in place to `workflow_runs`;
- `ingestion_jobs` is renamed in place to `workflow_jobs`;
- Python records and domain state use `WorkflowRun` and `WorkflowJob` names;
- every run stores a nonblank `workflow_kind` independently of an individual job's `task_type`;
- the existing PostgreSQL lease, retry, checkpoint, idempotency, and audit behavior is reused;
- current `/runs` routes and source-facing `task_type` behavior remain compatible.

## Migration and data preservation

Revision `20260802_0004` renames tables, indexes, and table-owned constraints instead of copying
data. PostgreSQL updates foreign-key targets during the table rename, preserving source discovery,
audit, and knowledge-claim lineage. Existing run kinds are backfilled from the earliest job ordered
by creation time and ID. A legacy run with no job receives the explicit migration-only kind
`system.unknown`; new application runs always derive their kind from the requested task type.

The knowledge-claim validation function previously contained a textual reference to
`ingestion_runs`. The migration replaces that PL/pgSQL function with a `workflow_runs` reference on
upgrade and restores the legacy reference on downgrade.

The PostgreSQL preservation test performs a real round trip:

1. downgrade to revision `20260729_0003`;
2. insert a legacy project, ingestion run, job, audit event, entity, and extraction claim;
3. upgrade to head and verify stable IDs, references, renamed tables, and derived kind;
4. downgrade again and verify the same lineage through the legacy names;
5. restore the test database to head even if an assertion fails.

## Architecture decision

A second queue, broker, or worker framework would duplicate retry and observability semantics
before there is evidence that the modular monolith needs independent scaling. C2.3a therefore keeps
the PostgreSQL leased queue and registered-handler boundary. `workflow_kind` describes the business
workflow; `task_type` continues to route one leased job to its concrete handler. They are equal for
the current one-job workflows but are intentionally separate concepts for future multi-step runs.

## Security and privacy

- the migration does not export, duplicate, or log source or model content;
- audit events remain append-only and retain their original run identifiers;
- knowledge claims retain their extraction-run references;
- queue payloads remain bounded application data rather than executable instructions;
- no new network service, credential, paid API, or telemetry dependency is introduced.

## Deliberately deferred to C2.3b and later

- registration of `knowledge.extract` as a durable handler;
- source-text loading and durable model-invocation/claim persistence;
- extraction preflight, commands, and APIs;
- extraction UI and real NTE PostgreSQL acceptance;
- conflict processing, human review actions, and snapshot publication.
