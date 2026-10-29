# M0–M18 历史能力记录

> 以下保留重组前 README 的里程碑描述，包含旧的完成度措辞。
> 它是历史记录，不作为 M19 当前验收或商业成熟度证明。当前状态见 ../../README.md。

## Current status

The repository has reached **GameCrafter 1.0.0 through M18**, a reproducible, self-diagnosing mature local product release. The original NTE-to-English-
TikTok workflow remains the primary validation path; later capabilities extend it without
weakening evidence, privacy, human control, or the strict zero-paid-API boundary.

The default Chinese workspace now keeps one current task above the fold. A first-time user can
import the allowlisted NTE English homepage without typing a URL; optional article discovery and
diagnostic metrics stay collapsed until they are needed. Mobile navigation remains a single
horizontal rail instead of wrapping into an ambiguous second row.

Knowledge review now exposes a project-wide pending count and a direct next-item action instead of
leaving users to search recent extraction batches. Pending and deferred Claims remain visibly
actionable; submitted Claims move into a checked, collapsed completed section; and every submission
opens the next outstanding Claim, even when it belongs to another game entity. Decision, entity-
correction, and conflict-closure reasons use bilingual presets, with manual text reserved for an
explicit Other choice. This improves clarity without weakening append-only human approval.

M14 turns the verified product into a reproducible release: Python production/development
dependency graphs and artifact hashes are committed, Docker base images and GitHub Actions are
pinned to immutable digests/commits, CI installs only the locked graph, and backend/frontend/API
versions agree on `1.0.0`. See [`docs/security/reproducible-releases.md`](docs/security/reproducible-releases.md)
for the controlled update procedure.
Repository security reports and contributions follow [`SECURITY.md`](SECURITY.md) and
[`CONTRIBUTING.md`](CONTRIBUTING.md). Long-term update coverage and the intentional pnpm 11
automation exception are recorded in
[`docs/security/dependency-maintenance.md`](docs/security/dependency-maintenance.md).

The production stack now defaults to the zero-cost local Ollama adapter and checks that the exact
configured model is actually present before enabling Curator or Reviewer actions. The live NTE
English homepage has been verified through four extraction chunks and the independent Reviewer:
the Curator retained eight exact-quote candidates, while Reviewer 1.2 approved six and rejected two
ambiguous name mentions. Internal entity keys are not sent to the model, and user-confirmed names
remain scope hints rather than evidence.

M13 closes the operational blind spot that previously let a healthy page hide a stopped worker:

- the worker now persists a bounded liveness heartbeat, while the authenticated Account workspace
  reports database connectivity, worker freshness, queued/leased/failed counts and expired leases;
- missing and stale workers produce explicit attention guidance without making the API container
  unavailable, so the user can still open the diagnostic and recovery interface;
- every HTTP response carries a bounded request ID and server logs correlate method, safe path,
  status and duration without logging query strings, credentials or private request bodies.

The M9–M12 maturity pass adds:

- versioned, restorable project backups with database-record and SHA-256 object verification,
  bounded ZIP expansion, traversal/link/undeclared-object rejection and rollback on failure;
- an Account recovery interface that works even when no project remains, assigns restored data to
  the authenticated local owner, and applies the existing project quota;
- owner-controlled team role changes and atomic team/project ownership transfer, with immediate
  permission changes and durable security events;
- persistent privacy-preserving login throttling, exact-Origin protection for authenticated
  browser writes, CSP, framing/MIME/referrer/device-permission security headers and visible keyboard
  focus;
- a mature local-product acceptance matrix defining what is verified and what deliberately remains
  outside the zero-cost local boundary.

The M6–M8 completion release adds:

- real public trend retrieval through no-key Google News RSS and GDELT DOC, with optional official
  YouTube Data API free quota and a deliberately manual, verified TikTok path;
- private TXT, Markdown, VTT transcript, JSON, and user-owned GDD evidence import, stored only in
  content-addressed local object storage;
- an eight-role constrained Agent topology, adding deterministic Source/Provenance Steward and GDD
  Architect roles while keeping security policy outside model control;
- optional local accounts with scrypt password hashing, opaque revocable sessions, project tenant
  isolation, owner/editor/reviewer/viewer RBAC, expiring single-use invitations, revocation, and
  local quotas;
- complete project ZIP export/restore, typed-confirmation project deletion with unreferenced-object cleanup,
  and guarded account deletion;
- GDD Studio with exact source offsets, chapter hierarchy, separately reviewed assumptions, and
  immutable canonical revisions;
- deterministic multi-source synthesis over approved snapshots, explicitly separating corroborated
  values from single-source facts without generating new claims;
- an updated requirements matrix and architecture DAGs covering M1.1 and M6–M8 local behavior.

M5 adds:

- a beginner-oriented five-step journey from Sources to an approved export, with one visible next
  action instead of requiring users to infer the tab order. The M16 interface promotes this into a
  persistent production route, automatically opens the server-recommended task, and moves GDD,
  Runs, and Account into a clearly secondary tools layer;
- a project overview API and UI metrics for evidence, Claims, verified trends, script versions,
  successful/active/attention runs, and the truthful zero-dollar API cost;
- deterministic trend normalization, exact-duplicate detection, related-event clustering,
  freshness labels, fingerprints, and disclosed processing-rule versions over immutable raw
  observations;
- an explicit human retry command for terminal workflow failures, preserving the original run and
  adding an audit event instead of silently restarting work;
- a production-preview Docker stack with migration, API, worker, PostgreSQL, object storage, Nginx,
  dependency health checks, and a single local URL;
- real Chromium desktop/mobile acceptance with horizontal-overflow and console-error checks.
- a readable Campaign Strategist brief that turns the selected trend and frozen knowledge snapshot
  into one explicit marketing direction, English video topic, core message, timed content plan,
  usable proof facts, evidence link, risks, alternatives, and a direct handoff to script creation;
  the brief is deterministic, versioned, auditable, and keeps paid API cost at zero.

Implemented through M4:

- an eight-role, versioned specialist topology coordinated by the durable Harness: Source and
  Provenance Steward, Knowledge Curator, Knowledge Reviewer, Trend Analyst, Campaign Strategist,
  Script Writer, Quality/Compliance Critic, and GDD Architect;
- typed artifact handoffs instead of free-form Agent chat, with local-model versus deterministic
  execution disclosed per role through `GET /agents`;
- an independent loopback-only Ollama knowledge Reviewer with strict structured decisions,
  exact claim-ID coverage, redacted failures, risk codes, bounded rationales, and token accounting;
- extraction reuse for the same evidence/entity/prompt/schema target, per-batch Claim display,
  deterministic duplicate handling, taxonomy-risk routing, and a maximum 15-fact proposed pack;
- separate immutable Agent-review and human-review ledgers, plus one-command human confirmation of
  clear keep/remove suggestions while unresolved candidates retain individual controls;
- a bilingual pre-review interface with keep/remove/needs-human counts, filtered low-value items,
  evidence-linked rationale, durable run progress, and unchanged human publication gates;

- a modular-monolith project layout;
- a FastAPI health endpoint;
- a React health/status page;
- project-local Python environment and repeatable scripts;
- baseline tests and continuous integration;
- product, architecture, migration, and roadmap documentation.
- PostgreSQL 17 plus pgvector Docker Compose configuration;
- Alembic migrations for projects, generic workflow runs, leased jobs, and audit events;
- a bounded-retry Python worker shell with durable checkpoints and idempotent run creation;
- API liveness and database-readiness endpoints;
- PostgreSQL migration and queue verification in CI;
- canonical source, multilingual family, discovery-candidate, immutable-version, and evidence-asset
  contracts;
- content-addressed local object storage with atomic writes, deduplication, limits, and traversal
  protection;
- M1-B migration upgrade and downgrade verification in CI.
- exact official-host and path allowlists for the NTE global and mainland sites;
- HTTPS URL normalization, redirect revalidation, public-DNS checks, response limits, and
  per-run access-budget contracts;
- a bounded HTTP page fetcher plus an isolated Playwright fallback restricted to approved
  homepage paths;
- deterministic NTE metadata adapters for English, Simplified Chinese, Japanese, and mainland
  Chinese pages;
- direct homepage/article adaptation and bounded listing-page candidate discovery.
- registered `source.discover` and `source.capture` durable worker handlers;
- per-job robots enforcement, request budgets, host spacing, and in-process concurrency gates;
- quick/targeted candidate filtering with explicit listing-page and candidate limits;
- direct official-URL import and same-project capture of human-selected candidates;
- deterministic visible-text extraction that excludes executable page sections;
- bounded same-host PNG, JPEG, WebP, and GIF capture with byte and signature checks;
- content-addressed raw HTML, normalized text, and image storage;
- transactional source creation, immutable version lineage, conditional HTTP reuse, and
  fingerprint-based no-change detection;
- source audit events and explicit retry/terminal failure classification.
- project-scoped source, candidate, and run APIs with bounded command schemas;
- atomic human candidate selection and capture enqueue with strict idempotency conflict checks;
- resumable SSE audit streams with durable event cursors and terminal closure;
- responsive Sources/Runs product interfaces, default Simplified Chinese, and remembered English
  switching;
- four NTE official-site quick profiles, filtered targeted discovery, and direct official-URL
  import;
- visible candidate provenance, evidence counts, checkpoints, and actionable terminal failures.
- controlled game-knowledge entity types, predicates, and typed candidate values;
- immutable model claims with exact source-version evidence spans and complete extraction
  provenance;
- append-only human reviews that preserve original and approved edited values separately;
- deterministic conflict-group and immutable knowledge-snapshot contracts;
- PostgreSQL guards for evidence-required approval, unresolved-conflict publication blocking, and
  immutable review/snapshot lineage.
- a provider-neutral `ModelGateway` with disabled, exact offline-replay, loopback-only local
  Ollama, and dependency-injected OpenAI Responses adapters;
- strict structured claim output, exact quote/range validation, request fingerprints, redacted
  provider errors, and token-usage contracts;
- bounded local-model output (up to eight high-value claims per chunk) with deterministic exact-quote
  offset repair and per-candidate rejection when a small model returns unsupported evidence;
- a zero-API-cost runtime boundary: cloud execution remains uncomposed, while optional local
  Ollama traffic is restricted to loopback and uses an injected transport.
- a paragraph/sentence-aware deterministic Unicode chunker with exact source offsets, stable chunk
  IDs, a 4,000-character limit, and 400-character overlap;
- a sequential fail-closed extraction Harness with request/result fingerprint checks, exact
  overlap deduplication, aggregate usage, and a replayable invocation manifest;
- a strict offline-fixture loader plus a source-attributed English NTE homepage replay whose tests
  actively block network access and report zero token usage.
- a data-preserving `ingestion_runs`/`ingestion_jobs` to `workflow_runs`/`workflow_jobs` migration;
- a nonblank `workflow_kind` discriminator backfilled from each legacy run's initial task;
- reusable PostgreSQL-leased workflow execution for source, knowledge, and later marketing jobs
  without adding a second queue stack;
- upgrade/downgrade coverage that preserves run, job, audit, and knowledge-claim lineage while the
  existing `/runs` source experience remains compatible.
- a registered `knowledge.extract` worker handler on the shared PostgreSQL lease queue;
- verified normalized-text loading with byte, SHA-256, UTF-8, project, source-version, and subject
  integrity gates;
- durable redacted per-chunk invocation lifecycles and an immutable whole-document result marker;
- atomic candidate-claim, exact-evidence, extraction-result, and audit persistence with idempotent
  retry behavior;
- project-scoped extraction command/result/claim APIs with zero-cost provider preflight;
- disabled-by-default execution with exact offline replay and loopback-only local Ollama as the
  runnable zero-API-cost modes.
- project-scoped game-entity create/list APIs with server-owned stable keys and duplicate-safe
  identity handling;
- append-only entity correction and terminal archival history without rewriting claims or evidence;
- latest-first immutable source-version read models with normalized-text availability;
- a non-mutating extraction-capability preflight that distinguishes disabled, local Ollama,
  missing, invalid, mismatched, incomplete, and exact offline replay states;
- filterable unreviewed-claim reads with server-returned evidence quotes and source/version metadata.
- a responsive Knowledge workspace that keeps entity identity, immutable evidence-version choice,
  exact-replay capability, extraction progress, candidate claims, and exact evidence in one flow;
- SSE progress updates with a two-second polling fallback while a run remains active, preventing a
  completed or failed background job from appearing permanently stuck;
- beginner-safe game-entity creation plus append-only correction and archival controls;
- explicit zero-cost disabled/mismatch states, Knowledge-to-Runs trace navigation, and a Sources
  shortcut when no evidence exists;
- grouped candidate claims and a server-rendered evidence inspector that never re-slices Unicode
  offsets in the browser;
- default Simplified Chinese, remembered English switching, and desktop/mobile browser coverage.
- a real PostgreSQL acceptance that binds the reviewed public NTE snapshot to a unique immutable
  source version and runs it through the leased `knowledge.extract` worker;
- acceptance assertions for command idempotence, zero-token exact replay, atomic Claim/evidence
  persistence, source lineage, audit completion, and redacted result reads;
- a safety-gated PowerShell acceptance command that only accepts disposable localhost databases
  whose names contain `test` or `acceptance`.
- a versioned deterministic conflict policy that compares only immutable Claims sharing the same
  subject, controlled predicate, and exact locale/region/time/game-version scope;
- conservative cardinality rules: only game name, release status/date, and primary genre are
  treated as single-valued; every other differing value is marked `possibly_coexisting`;
- serialized, idempotent conflict reconciliation with explainable member basis, safe handling of
  human-closed groups, project-scoped reads, and append-only reconciliation audit events;
- conflict reconcile/list APIs returning unreviewed candidates with their existing exact-evidence
  read models, without model calls, confidence ranking, or automatic resolution.
- an explicit conflict-check control embedded in the bilingual Knowledge workspace;
- responsive conflict and possible-coexistence cards that expose values, candidate counts, status,
  policy version, and deterministic classification basis;
- one-click navigation from every conflict member to its exact source evidence, while leaving all
  selection, approval, and resolution decisions to the later human-review workflow.
- append-only approve, approve-with-edit, reject, and defer commands whose exact retries are
  idempotent and whose conflicting key reuse is rejected;
- shared typed-value normalization for model candidates and human edits, evidence-required
  approval, visible latest status, and complete review history without rewriting any Claim;
- guarded conflict closure: resolution requires a final decision for every member, at least one
  approval, and exactly one retained normalized value for a single-valued conflict;
- explicit dismissal with a human reason, complete resolution metadata, causal audit events, and
  PostgreSQL-enforced command lineage;
- responsive bilingual review/closure controls beside the exact evidence, with desktop and mobile
  browser verification.
- a project-wide publication-readiness service that reports every unreviewed, deferred, conflicted,
  archived, or incomplete-lineage blocker before attempting a write;
- serialized and idempotent knowledge publication with deterministic content digests, monotonically
  increasing versions, and exact approving-review/evidence lineage;
- immutable snapshot history and member reads, enforced by PostgreSQL triggers and covered by real
  PostgreSQL publication, retry, audit, and mutation-rejection tests;
- responsive bilingual publication controls and version history in the Knowledge workspace, with
  desktop and mobile browser verification.
- immutable manual trend observations with source URL, observation time, market, type, keywords,
  optional metric, verification notes, strict HTTPS validation, and idempotent retry;
- immutable marketing tasks that freeze one published knowledge snapshot plus TikTok platform,
  English-market audience, objective, output language, and duration;
- deterministic four-dimension topic-fit analysis covering freshness, market alignment, source
  completeness, and approved-knowledge relevance without a model call;
- explicit risk disclosures, exact trend/snapshot lineage, append-only topic decisions, and a
  single-current-approved-topic human gate;
- a bilingual responsive Marketing workspace verified on Chinese desktop and English mobile.
- immutable script runs that freeze the exact marketing task, approved topic decision, and
  published knowledge snapshot;
- deterministic English TikTok generation with section timelines, voiceover, on-screen text,
  visual direction, hashtags, and exact knowledge/trend references at zero model cost;
- a versioned 100-point evaluator covering timeline, hook, evidence, CTA, TikTok structure, and
  schema safety, plus a configurable revision threshold and a hard automatic-revision budget;
- append-only generated, human-edited, and auto-revised versions with canonical SHA-256 digests;
- mandatory final human approval before Markdown or JSON export, with immutable export receipts;
- a bilingual responsive Create workspace for preview, structured editing, evaluation, revision,
  final review, and local file download.

Deliberately not implemented:

- binary office-document OCR/import (the private path accepts bounded UTF-8 text formats);
- a live NTE acceptance capture committed as product evidence;
- embeddings or retrieval over approved knowledge snapshots;
- TikTok scraping or an unverified TikTok API connection;
- cloud LLM calls, RAG, or model-generated marketing copy (local Ollama knowledge roles are live);
- payment processing or a “free forever” public cloud-hosting claim. Local account isolation,
  resource quotas, and team collaboration are implemented; monetary billing would contradict the
  confirmed strict zero-cost boundary and requires a later commercial deployment decision.

The earlier README described several of these as if they already existed. They did not. The original placeholder modules remain traceable in Git history and are documented under [`legacy/`](../../legacy/README.md).
