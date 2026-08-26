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
| M7 | Small-team collaboration | RBAC, approval, audit, revocation, team isolation |
| M8 | Structured GDD Studio | chapter-level evidence, assumptions, revisions, shared knowledge |
| M9 | Verified disaster recovery | versioned export, strict archive validation, exact restore, no partial writes |
| M10 | Complete team governance | role changes, atomic ownership transfer, project continuity, security audit |
| M11 | Local security hardening | persistent login throttle, exact-origin session protection, browser security headers |
| M12 | Mature local release | accessible operation, recovery UX, full production/database/browser acceptance |
| M13 | Self-diagnosing operations | worker heartbeat, queue/lease diagnosis, request correlation, visible remediation |

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
- M1-C C5 implements complete-project readiness checks, serialized idempotent publication,
  deterministic content digests, immutable version history, exact approval/evidence lineage,
  PostgreSQL enforcement, and bilingual publication controls. The M1 Knowledge Hub vertical slice
  is complete.
- M2 implements immutable user-verified public trend observations with source/time/region/metric
  provenance, HTTPS and timezone validation, idempotent retry, and honest manual-source labelling.
- M3 implements immutable snapshot-bound marketing tasks, deterministic four-dimension fit,
  explainable risks and evidence links, append-only review history, and a single-approved-topic
  human gate.
- M4 implements evidence-bound English TikTok script generation, canonical version digests,
  deterministic 100-point evaluation, a hard automatic-revision budget, human-edited versions,
  mandatory final approval, and audited Markdown/JSON export. This closes the first complete local
  product slice.
- M5 is complete: it adds a five-step guided journey, project progress/value metrics, audited
  human retry of terminal jobs, deterministic trend normalization/deduplication/clustering,
  production-preview containers, and desktop/mobile Chromium acceptance. This is the portfolio-ready
  local release.

M1.1 and M6–M13 are complete for the mature local-product boundary. M1.1 adds bounded private text,
transcript, and owned-GDD evidence plus real public trend connectors. M6 adds optional local
identity, isolation, quotas, portable export, project deletion, and guarded account deletion. M7
adds four-role RBAC, expiring hashed invitations, and immediate revocation. M8 adds source-bound GDD
chapters, exact offsets, separately reviewed assumptions, and immutable revisions. M9 replaces the
export-only backup claim with a versioned, hash-verified recovery path. M10 adds immediate role
changes and atomic ownership transfer for a team and all its projects. M11 adds persistent login
throttling, exact-Origin protection for cookie writes, CSP and browser hardening headers. M12 adds
the visible recovery experience and closes the local database, production and browser release
gates. M13 makes background execution observable through persistent worker liveness, aggregate
queue/lease state and bounded request correlation. Payment
processing and anonymous public hosting remain outside scope because they contradict the confirmed
zero-cost local boundary and would require a separate commercial/privacy decision.
