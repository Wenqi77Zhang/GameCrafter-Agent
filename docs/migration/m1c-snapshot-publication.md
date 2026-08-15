# M1-C C5 immutable knowledge publication

C5 completes the first Knowledge Hub vertical slice by turning the current set of human-approved
Claims into an explicit, immutable project knowledge version. It does not silently publish when a
review is recorded or a conflict is closed.

## Publication policy

The readiness read model and publication command share one fail-closed planner:

- every current Claim in the project needs a latest final review; `defer` is not final;
- at least one Claim must be approved;
- every approved Claim requires exact source-version evidence and complete project lineage;
- an archived entity cannot contribute approved knowledge;
- every open conflict blocks the entire project snapshot;
- differing values must have a reconciled conflict group;
- a single-valued predicate can retain only one normalized approved value, including values created
  by human edits;
- all current approvals are included automatically, so callers cannot publish a selective subset.

Readiness returns structured blockers, counts, the next version, and—only when publishable—the
deterministic content digest.

## Atomic and idempotent command

Publication locks the project, rebuilds the plan inside the transaction, and inserts the snapshot,
members, and causal audit event together. The digest covers sorted approved values and their exact
entity-revision, approving-review, evidence-span, source, and immutable source-version lineage.
Optional notes are snapshot metadata and do not change that content digest.

The project-scoped command key has two outcomes: an exact retry returns the original snapshot, while
reuse with different notes or content fails. A new command key intentionally creates the next
immutable version even when the approved content is unchanged.

## Delivery and verification

The Knowledge API exposes publication readiness, create/list, and exact snapshot reads. The
bilingual responsive workspace shows blockers, publishes only when ready, and renders immutable
version/member/evidence history.

Verification covers:

- SQLite service and API behavior, OpenAPI contracts, and fail-closed policy cases;
- PostgreSQL migration upgrade/downgrade, exact retry, version creation, causal audit, and database
  rejection of published-lineage mutation;
- frontend type checking, unit tests, production build, and Chinese desktop/English mobile browser
  smoke checks without console errors or horizontal overflow.

C5 does not add embeddings, retrieval, trend collection, live model calls, or marketing generation.
Those remain later milestones and must consume an explicit snapshot ID rather than mutable reviews.
