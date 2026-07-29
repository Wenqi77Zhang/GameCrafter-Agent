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
- M1-B B4 APIs/SSE/Sources/Runs interfaces, M1-C claim review, and M1-D real NTE acceptance remain
  unimplemented.
