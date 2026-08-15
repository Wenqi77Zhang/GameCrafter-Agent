# GameCrafter v2 product baseline

Status: confirmed on 2026-07-27.

GameCrafter is a long-term personal product, portfolio project, and potential commercial product. It is no longer a four-day team assignment.

## Product

GameCrafter is an evidence-aware game knowledge and marketing workspace for independent game developers.

The first complete slice:

1. imports public game evidence;
2. builds a human-reviewed Game Knowledge Hub;
3. retrieves real trend signals;
4. explains game, platform, market, audience, and goal fit;
5. requires human topic approval;
6. creates a structured marketing brief and TikTok script;
7. evaluates and revises low-score sections;
8. preserves versions and requires final human approval.

## First validation case

- Game: NTE: Neverness to Everness (《异环》)
- Developer: Hotta Studio, part of Perfect World
- Target platform: TikTok
- Markets: United States, United Kingdom, Canada, Australia, and New Zealand
- Audience: potential new players in English-speaking markets
- Output: a 25–35 second English vertical-video marketing script

## First-release boundaries

The first release is local and single-user. It does not include accounts, multi-tenancy, team collaboration, billing, a complete GDD Studio, video rendering, or unauthorized TikTok scraping.

Public sources must not be described as an internal GDD. For existing games, the Knowledge Hub creates a sourced Public Game Intelligence Profile. User-owned internal documents may be supported locally, but online private uploads require later authentication and isolation work.

## M1 official-source policy

- The NTE validation profile supports the global official site's English, Simplified Chinese, and
  Japanese sections plus the separate mainland-China official site.
- Discovery is bounded and human-triggered. It offers quick discovery, filtered historical
  discovery, and direct official-URL import; there is no silent scheduled crawling in the first
  release.
- Candidates require human selection before full capture. Original HTML, normalized text,
  provenance metadata, and bounded relevant images form an immutable local evidence bundle.
- HTTP is the primary capture mechanism. A site adapter may permit one controlled Playwright
  fallback for pages that require JavaScript.
- Official-language variants remain separate evidence and may be linked as one content family;
  they are never silently merged into one fact.
- The local filesystem implements the first `ObjectStorage` adapter. Raw evidence and private local
  data remain gitignored; later storage providers stay behind the same application port.

## M1 knowledge-review policy

- A model-produced claim is never an approved fact. Every new claim requires an exact evidence
  span and an explicit human decision.
- M1-C uses controlled entity and predicate vocabularies. Unsupported claims remain unclassified
  rather than allowing a model to silently expand the ontology.
- Human decisions are approve, approve with edit, reject, or defer. The original model value and
  every review decision remain immutable and attributable.
- Conflict detection is deterministic over subject, predicate, normalized value, region, locale,
  effective time, and game version. A model confidence score cannot resolve a conflict.
- Approved facts affect later workflows only after the user explicitly publishes an immutable
  knowledge snapshot. Open conflicts block publication.
- C2 runs in strict zero-API-cost mode. Only disabled and exact offline-replay gateways may be
  composed into the runnable application; automated tests must fail if they attempt a real model
  network request.
- C2.2 chunks normalized text without rewriting it, using the versioned 4,000-character maximum and
  400-character overlap. Offsets are Python Unicode code-point indices; delivery interfaces must
  render server-returned evidence rather than re-slicing text with JavaScript UTF-16 offsets.
- C2.2 uses one sequential Knowledge Curator Harness, not ReAct or an autonomous multi-Agent
  conversation. Any chunk failure rejects the whole document result; only identical
  predicate/value/evidence candidates are deduplicated, and every invocation remains traceable.
- C2.3a generalizes the original source-ingestion tables into `workflow_runs` and `workflow_jobs`.
  Every run has a nonblank `workflow_kind`; source ingestion, knowledge extraction, and later
  marketing workflows reuse one PostgreSQL leased queue rather than introducing a parallel broker
  or worker system.
- The rename is data-preserving and reversible. Existing run IDs, job IDs, audit references,
  knowledge-claim extraction references, idempotency behavior, `/runs` routes, and current source UI
  semantics remain stable.
- C2.3b registers `knowledge.extract` on that shared worker. The handler accepts only project-bound
  immutable source-version and subject IDs, verifies the normalized object byte count, digest,
  encoding, and configured size limit, then fails the whole document closed on any chunk error.
- Each chunk attempt persists redacted operational metadata only: hashes, offsets, provider/model
  identifiers, response ID, usage, claim count, status, and safe error code. Prompt bodies, source
  bodies, response bodies, keys, and local object paths are excluded from invocation rows and API
  read models.
- Candidate claims, exact evidence spans, the immutable result marker, and its audit event commit in
  one transaction. A committed result is the retry idempotency boundary; PostgreSQL lineage triggers
  reject cross-project or wrong-workflow extraction records.
- The extraction command is unavailable while the model provider is disabled and is accepted in C2
  only when a validated local fixture exactly covers the deterministic request fingerprints. This
  preserves strict zero API cost; no approximate fixture or paid fallback exists.
- C2.4a keeps stable entity identity immutable while allowing human-entered display names and aliases
  to be corrected through append-only revisions. Archival is terminal, old values remain auditable,
  and existing claims are never silently moved to another subject.
- C2.4a exposes immutable source versions latest-first with explicit historical selection, plus a
  read-only capability preflight that reports why an exact zero-cost replay is or is not available.
  Candidate reads remain explicitly unreviewed and return server-stored evidence quotes with source
  metadata; C2.4a does not approve, reject, or publish knowledge.
- C2.4b keeps extraction in a dedicated Knowledge workspace. It defaults to the latest available
  immutable evidence version but permits explicit historical selection, displays capability reason
  codes without implying a model call, and keeps the user on the page while the durable run starts.
- Progress is derived only from persisted run and audit state. Candidate claims remain visibly
  unreviewed, are grouped by controlled predicate, and open an evidence panel using server-returned
  quotes and provenance. The interface does not expose review or publication actions before their
  guarded backend commands exist.
- If no entity or evidence version exists, the workspace offers a direct route to create the game
  identity or add sources. Entity corrections append history; archival is explicit and terminal.
  Simplified Chinese is the product default and English remains a remembered option.
- C2.5 acceptance uses the committed, source-attributed public NTE snapshot rather than a current
  live-site capture. It rebinds that reviewed response to a unique immutable version only inside a
  disposable PostgreSQL test database, then verifies the real leased worker and persistence
  constraints with zero input, output, and total tokens.
- The acceptance command rejects remote hosts and database names without `test` or `acceptance`.
  It does not delete its auditable rows or print credentials. Live-site capture evidence remains a
  separate, explicitly uncompleted acceptance boundary.
- C3a compares Claims only when project, subject, predicate, and the precomputed scope fingerprint
  match and at least two distinct normalized values exist. Confidence never decides the relation.
- Policy `claim-conflict-v1` treats `game.name`, `release.status`, `release.date`, and
  `genre.primary` as single-valued in one exact scope. Other predicates fail conservatively to
  `possibly_coexisting` because developers, aliases, platforms, features, and descriptions may
  legitimately have multiple supported values.
- Reconciliation is serialized per project and idempotently appends missing groups/members. It
  never reopens a resolved or dismissed group; instead it reports that a closed scope was skipped
  so a later human-review workflow can handle new evidence explicitly.
- C3b keeps conflict detection an explicit user action. It displays `conflicting` and
  `possibly_coexisting` separately, localizes group status, and exposes the policy version and
  classification basis instead of hiding the deterministic rule behind a score.
- Selecting any conflict member selects the same immutable Claim in the candidate browser and
  opens its exact source-version evidence. C3b never picks a winner, edits a Claim, approves a
  value, closes a group, or publishes a snapshot.
- C4 reviews are append-only. `approve` copies the immutable candidate value;
  `approve_with_edit` stores a separately typed and normalized approved value; `reject` and
  `defer` cannot carry a value. Every approval requires exact Claim evidence and every command
  requires a nonblank bounded human reason. Human-edited JSON is capped at 16,384 UTF-8 bytes
  before validation or persistence.
- Review and conflict-closure commands require idempotency keys. Replaying the exact command
  returns the existing decision; reusing a key for different content is rejected. Audit payloads
  record decision identity and type without duplicating the approved value or human reason.
- Resolving a conflict requires a latest non-deferred decision for every member and at least one
  approved value. A `conflicting` single-valued group must converge on exactly one approved
  normalized value; a `possibly_coexisting` group may retain multiple approved values. Dismissal
  remains an explicit reasoned human override.
- The browser displays current status and all prior reviews beside the exact evidence. A new
  review never deletes or edits a prior review, and closing a group never publishes knowledge.
- The confirmed M1-C order is C2.3a workflow substrate, C2.3b durable extraction, C2.4 extraction
  UI, C2.5 NTE PostgreSQL acceptance, C3 conflicts, C4 reviews, and C5 publication.
- The committed NTE replay is a small, source-attributed snapshot of public English official-site
  metadata. It is test evidence only, not an internal GDD, current live-site proof, or a live model
  response.
- The first cloud-provider adapter targets the OpenAI Responses API behind a provider-neutral
  `ModelGateway`, but C2.1 only implements its dependency-injected request adapter and simulated
  tests. It does not install a model SDK, read an API key, construct a network client, or perform a
  live call.
- If cloud execution is explicitly approved in a later baseline change, every real extraction must
  pass a per-run egress preflight. Only normalized public source text and minimum provenance
  metadata may leave the machine; raw HTML, images, secrets, object paths, private documents, and
  unrelated logs remain excluded.
- Any later OpenAI call must use minimized logging and `store: false`, while product copy must still
  disclose that provider abuse-monitoring retention can apply unless the organization has eligible
  data-retention controls.

## Architecture policy

- modular monolith before microservices;
- deterministic state graphs around constrained specialist nodes;
- local ReAct only where research tools are needed;
- evaluator–optimizer loops with explicit limits;
- human approval before topic selection and final export;
- versioned skills, prompts, rules, sources, and outputs;
- provider adapters instead of vendor coupling;
- no MCP service unless cross-application reuse or independent permissions justify it.

## Change control

Changes to the product positioning, first complete slice, default validation case, data boundary, agent pattern, main technology stack, or milestone order require explicit approval from the project owner and synchronized documentation updates.
