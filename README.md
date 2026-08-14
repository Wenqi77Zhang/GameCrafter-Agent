# GameCrafter

> An evidence-aware game knowledge and marketing workspace for independent game developers.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Frontend](https://img.shields.io/badge/React-TypeScript-149ECA?logo=react&logoColor=white)](https://react.dev/)
[![Backend](https://img.shields.io/badge/FastAPI-Pydantic-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

GameCrafter is being rebuilt from an early architecture shell into a long-term product for independent game developers. It will organize game information into a traceable knowledge hub, connect that knowledge to real market signals, and help users create, evaluate, revise, and approve marketing scripts.

The first complete product slice focuses on marketing a real game to English-speaking TikTok audiences. The default validation case is **NTE: Neverness to Everness (《异环》)**.

## Current status

The repository is currently in **M1-C C3a: deterministic conflict service**.

Implemented through M1-C C3a:

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
- a provider-neutral `ModelGateway` with disabled, exact offline-replay, and dependency-injected
  OpenAI Responses adapters;
- strict structured claim output, exact quote/range validation, request fingerprints, redacted
  provider errors, and token-usage contracts;
- a zero-cost runtime boundary: no model SDK, API key, network client, or live model call is
  constructed in C2.1.
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
- project-scoped extraction command/result/claim APIs with strict local replay preflight;
- disabled-by-default execution where only an exact offline fixture can be enqueued at zero cost.
- project-scoped game-entity create/list APIs with server-owned stable keys and duplicate-safe
  identity handling;
- append-only entity correction and terminal archival history without rewriting claims or evidence;
- latest-first immutable source-version read models with normalized-text availability;
- a non-mutating extraction-capability preflight that distinguishes disabled, missing, invalid,
  mismatched, incomplete, and exact offline replay states;
- filterable unreviewed-claim reads with server-returned evidence quotes and source/version metadata.
- a responsive Knowledge workspace that keeps entity identity, immutable evidence-version choice,
  exact-replay capability, extraction progress, candidate claims, and exact evidence in one flow;
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

Not implemented yet:

- document ingestion or an installed browser runtime by default;
- a live NTE acceptance capture committed as product evidence;
- conflict-review and claim-review UI, snapshot publication commands, embeddings, or an approved
  knowledge snapshot;
- live trend sources;
- live LLM calls, RAG, or marketing agents;
- authentication, multi-tenancy, billing, or team collaboration.

The earlier README described several of these as if they already existed. They did not. The original placeholder modules remain traceable in Git history and are documented under [`legacy/`](legacy/README.md).

## Target product workflow (M1–M4)

This is the planned workflow. M1-A implements the durable project, run, job, and audit foundation.
M1-B B1 adds source-evidence and object-storage contracts. B2 adds controlled access primitives
and NTE adapters. B3 registers durable discovery/capture handlers and immutable persistence. B4
exposes them through human-controlled product APIs, resumable run events, and the Sources/Runs
workspace.

```mermaid
flowchart LR
    subgraph Sources["Evidence sources"]
        A1["Official websites"]
        A2["Official news and patch notes"]
        A3["Official video transcripts"]
        A4["Official store pages"]
        A5["User-owned documents"]
    end

    subgraph Knowledge["Game Knowledge Hub"]
        B1["Capture source snapshots"]
        B2["Extract entities and claims"]
        B3["Detect versions and conflicts"]
        B4{"Human fact review"}
        B5["Publish knowledge snapshot"]
    end

    subgraph Marketing["Marketing Studio"]
        C1["Fetch real trend signals"]
        C2["Normalize, deduplicate, cluster"]
        C3["Rank candidates and explain fit"]
        C4{"Human topic approval"}
        C5["Create marketing brief"]
        C6["Generate structured script"]
        C7["Evaluate and revise low-score sections"]
        C8{"Human final approval"}
        C9["Export reusable deliverables"]
    end

    Sources --> B1
    B1 --> B2 --> B3 --> B4
    B4 -->|"approve"| B5
    B4 -->|"edit or reject"| B2
    B5 --> C3
    C1 --> C2 --> C3 --> C4
    C4 -->|"approve"| C5 --> C6 --> C7 --> C8
    C4 -->|"choose another"| C3
    C4 -->|"refresh signals"| C1
    C8 -->|"revise"| C6
    C8 -->|"approve"| C9
```

The graph is deliberately constrained. Specialized agent nodes operate inside a deterministic workflow; models do not form an unrestricted autonomous agent swarm. Human approval is required before topic selection and final export.

For an existing game, approved public evidence becomes a sourced **Public Game Intelligence Profile**, not a claimed internal GDD. Future trend connectors must use authorized sources. TikTok Creative Center data is manually verified or imported in the first release rather than collected through unauthorized scraping.

## Target software architecture

This is the target modular-monolith architecture. M1-A implements the API health/readiness
boundary, PostgreSQL adapter, migration layer, durable job queue, worker shell, and audit
foundation. M1-B B1 adds inward-facing source-evidence contracts and a local `ObjectStorage`
adapter. B2 adds `PageFetcher` and `SiteAdapter` boundaries with HTTP, Playwright, and NTE
implementations. B3 composes them into registered worker handlers and transactional source
persistence. B4 adds validated delivery commands, project-scoped read models, SSE run events, and
the bilingual human-control interface. M1-C C1 adds reviewable knowledge lineage and PostgreSQL
guards. C2.1 adds the zero-cost model boundary; C2.2 adds deterministic chunking, sequential
offline extraction orchestration, and the source-attributed NTE replay fixture. C2.3a generalizes
the durable run/job substrate so later knowledge and marketing workflows reuse the same queue.
C2.3b registers durable extraction, persists redacted invocation and exact-evidence lineage, and
exposes project-scoped commands and read models under exact offline-replay preflight.
C2.4a adds the stable delivery contracts required by the Knowledge interface: correctable entity
labels with immutable history, source-version selection, honest replay capability, and enriched
candidate/evidence reads. C2.4b composes those contracts into the bilingual, responsive Knowledge
workspace while keeping human review and publication out of scope until their guarded commands
exist. C2.5 proves the NTE fixture path against migrated PostgreSQL, the real leased queue, and the
production persistence constraints; it is not represented as a current live-site capture.

```mermaid
flowchart TB
    UI["React + TypeScript web app"]
    API["FastAPI HTTP and SSE API"]
    APP["Application commands and queries"]

    subgraph Domain["Domain modules"]
        DP["Projects"]
        DK["Knowledge"]
        DT["Trends"]
        DC["Campaigns"]
        DS["Scripts"]
        DR["Runs and audit"]
    end

    subgraph AgentRuntime["Agent runtime"]
        KG["Knowledge ingestion graph"]
        MG["Marketing workflow graph"]
        SK["Versioned skills and prompts"]
        HG["Human approval gates"]
    end

    subgraph Adapters["Infrastructure adapters"]
        MODELS["ModelGateway"]
        TOOLS["ToolProvider"]
        SOURCES["Source connectors"]
        SEARCH["Full-text and vector search"]
        STORAGE["Object storage"]
        TRACE["Tracing and metrics"]
    end

    DB[("PostgreSQL + pgvector")]

    UI --> API --> APP
    APP --> Domain
    APP --> AgentRuntime
    AgentRuntime --> Adapters
    Domain --> DB
    Adapters --> DB
    API -. "SSE status events" .-> UI
```

See [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md) for the knowledge-ingestion and marketing state graphs, data trust boundaries, and design rationale.
See [`docs/migration/m1c-knowledge-workspace.md`](docs/migration/m1c-knowledge-workspace.md) for the C2.4b interface boundary and verification evidence.

## Repository layout

```text
apps/
  api/                  FastAPI application entrypoint
  worker/               Background worker entrypoint
  web/                  React and TypeScript frontend
src/gamecrafter/
  api/                  HTTP application factory and routes
  domain/               Implemented knowledge and run business rules
  application/          Commands, queries, and orchestration services
  infrastructure/       Database, source, model, storage, and tracing adapters
  config/               Validated settings
tests/                  Unit, integration, contract, and PostgreSQL tests
docs/                   Product, architecture, security, migration, and roadmap
scripts/                Setup, development, and verification helpers
legacy/                 Notes about the original placeholder shell
```

Future trend, campaign, script, and Agent-runtime packages are created only when their milestone
adds executable behavior; the active tree does not keep empty capability placeholders.

## Quick start

Prerequisites:

- Python 3.12 or newer;
- Node.js 22 or newer;
- pnpm 10 or newer;
- Docker Desktop with Linux containers.

From PowerShell:

```powershell
.\scripts\setup.ps1
.\scripts\database.ps1 up
.\scripts\start.ps1
```

The local services will be available at:

- web: `http://localhost:5173`
- API: `http://localhost:8000`
- API health: `http://localhost:8000/health`
- database readiness: `http://localhost:8000/ready`

The development launcher honors `GAMECRAFTER_API_HOST`, `GAMECRAFTER_API_PORT`, and
`GAMECRAFTER_LOG_LEVEL`; the URLs above are the defaults from `.env.example`.

Run all locally available checks:

```powershell
.\scripts\verify.ps1
```

Run the isolated NTE PostgreSQL acceptance only against a disposable localhost database. Its name
must contain `test` or `acceptance`:

```powershell
$env:GAMECRAFTER_TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/gamecrafter_test"
.\scripts\acceptance.ps1
```

The command migrates that disposable database, executes the zero-cost NTE extraction acceptance,
and never prints the connection URL. Acceptance rows are intentionally auditable, so do not point
the command at a personal product database.

Static HTTP capture does not require a browser download. Before a later JavaScript-rendered
acceptance test, inspect or install the isolated Chromium headless shell explicitly:

```powershell
.\scripts\browser.ps1 status
.\scripts\browser.ps1 install
```

Configuration names and safe placeholders are documented in [`.env.example`](.env.example). Never commit real API keys.
The PostgreSQL volume and raw local data are not stored in Git.

## Documentation

- [Product baseline](docs/product/baseline-v2.md)
- [System architecture and DAGs](docs/architecture/system-architecture.md)
- [Architecture decisions](docs/architecture/adr/)
- [Long-term roadmap](docs/roadmap.md)
- [M0 migration record](docs/migration/m0-restructure.md)
- [M1-A implementation record](docs/migration/m1a-persistence-foundation.md)
- [M1-B B1 evidence-contract record](docs/migration/m1b-source-evidence-contracts.md)
- [M1-B B2 source-access and adapter record](docs/migration/m1b-source-access-adapters.md)
- [M1-B B3 ingestion-handler record](docs/migration/m1b-source-ingestion-handlers.md)
- [M1-B B4 source-workspace record](docs/migration/m1b-source-workspace.md)
- [M1-C C1 knowledge-contract record](docs/migration/m1c-knowledge-review-contracts.md)
- [M1-C C2.1 model-gateway record](docs/migration/m1c-model-gateway.md)
- [M1-C C2.2 extraction-Harness record](docs/migration/m1c-extraction-harness.md)
- [M1-C C2.3a workflow-foundation record](docs/migration/m1c-workflow-foundation.md)
- [M1-C C2.3b durable-extraction record](docs/migration/m1c-durable-extraction.md)
- [M1-C C2.4a Knowledge-delivery API record](docs/migration/m1c-knowledge-delivery-api.md)
- [M1-C C2.4b Knowledge-workspace record](docs/migration/m1c-knowledge-workspace.md)
- [M1-C C2.5 NTE PostgreSQL acceptance](docs/migration/m1c-nte-postgres-acceptance.md)
- [M1-C C3a deterministic-conflict service](docs/migration/m1c-deterministic-conflicts.md)
- [Security baseline](docs/security/local-development.md)

## Development principles

- Build one real vertical slice before adding broad feature surface.
- Keep facts, model judgments, and human decisions visually and structurally distinct.
- Preserve source, time, version, region, and human-review evidence.
- Treat external content as untrusted input.
- Describe only capabilities that have actually been implemented and verified.
- Keep the core as a modular monolith until real scaling or isolation needs justify a service split.

## License

This project is licensed under the [MIT License](LICENSE).
