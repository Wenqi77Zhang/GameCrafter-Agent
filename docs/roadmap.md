# Long-term roadmap

Each milestone must produce a runnable slice, tests, a failure case, evidence, and an honest README status before the next milestone begins.

| Milestone | Outcome | Exit gate |
|---|---|---|
| M0 | Repository, API, web shell, tests, CI, architecture | clean setup, healthy API/web link, passing verification |
| M1 | NTE official-source Knowledge Hub slice | source snapshot to human-approved knowledge snapshot |
| M1.1 | News, video transcript, and local-file sources | unified provenance and conflict handling |
| M2 | Real trend candidate pool | non-preset data, source/time/region, failure and retry |
| M3 | Explainable fit and human topic approval | evidence, risks, bounded tools, auditable decision |
| M4 | Script, evaluation, revision, versions, export | bounded revisions and mandatory final approval |
| M5 | Public product and portfolio case | deployment, usability, responsive UI, observability |
| M6 | Accounts and individual commercialization | isolation, deletion/export, private storage, quotas |
| M7 | Small-team collaboration | RBAC, approval, audit, revocation, team billing |
| M8 | Structured GDD Studio | chapter-level evidence, assumptions, revisions, shared knowledge |

The course game-marketing requirements remain the minimum acceptance line for M2–M5, but the product is no longer constrained to a four-day team submission.

## Current delivery

- M0 is complete.
- M1-A implements the PostgreSQL, migration, durable run, leased-job, worker, and audit
  foundation.
- M1-B B1 implements source-evidence domain contracts, PostgreSQL tables, immutable version
  constraints, and the private local object-storage adapter.
- M1-B B2 implements exact official-site access policy, bounded HTTP and browser fetcher
  boundaries, and deterministic global/mainland NTE adapters.
- M1-B B3 implements durable discovery/capture handlers, robots and access scheduling, bounded
  official images, immutable version persistence, conditional reuse, and audit events.
- M1-B B4 implements human-controlled project/source/candidate/run APIs, atomic candidate
  selection, resumable SSE audit events, and bilingual Sources/Runs interfaces.
- M1-C C1 implements controlled entity/claim vocabularies, exact evidence spans, append-only human
  reviews, deterministic conflict-group contracts, immutable knowledge snapshots, and PostgreSQL
  approval/publication guards.
- M1-C C2.1 implements the provider-neutral `ModelGateway`, strict claim-output decoder, disabled
  gateway, exact offline replay, and a dependency-injected OpenAI Responses request adapter under a
  strict zero-API-cost policy.
- M1-C C2.2 implements deterministic 4,000/400 Unicode chunking, sequential fail-closed extraction
  orchestration, exact overlap deduplication, strict source-attributed replay-fixture loading, and a
  network-blocked English NTE homepage replay.
- M1-C C2.3a implements the generic `workflow_runs`/`workflow_jobs` substrate, a stable
  `workflow_kind`, data-preserving upgrade/downgrade, and reuse of the existing PostgreSQL leased
  queue while retaining the `/runs` source workflow.
- M1-C C2.3b implements the durable `knowledge.extract` handler, verified object loading, redacted
  invocation traces, atomic claim/evidence/result persistence, idempotent retries, and project-scoped
  APIs under disabled-or-exact-replay zero-cost preflight.
- M1-C C2.4a implements stable game-entity creation, append-only correction and archival history,
  immutable source-version selection reads, honest zero-cost capability preflight, and enriched
  candidate/evidence delivery contracts.
- M1-C C2.4b implements the bilingual responsive Knowledge workspace, entity and immutable-version
  selection, explicit zero-cost capability states, extraction start/progress, grouped candidate
  claims, exact evidence inspection, and navigation to Sources or the full run trace.
- M1-C C2.5 proves the reviewed public NTE snapshot through migrated PostgreSQL, the shared leased
  queue, zero-token exact replay, atomic candidate/evidence persistence, audit completion, and
  redacted read models. It deliberately does not claim current live-site capture evidence.
- M1-C C3a implements versioned deterministic conflict classification, serialized idempotent
  reconciliation, explainable member relations, closed-group protection, project-scoped delivery,
  audit events, and SQLite/PostgreSQL verification.
- M1-C C3b implements explicit conflict scanning, bilingual relation/status visualization,
  deterministic policy disclosure, and one-click navigation from every conflict member to exact
  evidence on responsive desktop and mobile layouts.
- M1-C C4 implements idempotent append-only Claim reviews, typed human edits, derived latest human
  state, guarded conflict resolution/dismissal, causal audit records, PostgreSQL command lineage,
  and bilingual evidence-adjacent review controls.
- M1-C C5 immutable snapshot publication remains unimplemented.
