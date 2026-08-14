# M1-C C4 append-only human review

C4 turns candidate inspection into explicit human control without rewriting model output or
silently treating a UI selection as truth.

## Command contracts

- `POST /api/projects/{project_id}/knowledge-claims/{claim_id}/reviews` appends `approve`,
  `approve_with_edit`, `reject`, or `defer` and requires `Idempotency-Key` plus a reason.
- `GET /api/projects/{project_id}/knowledge-reviews` returns complete project-scoped history with
  optional Claim and subject filters.
- `POST /api/projects/{project_id}/knowledge-conflicts/{conflict_group_id}/closure` records a
  reasoned `resolved` or `dismissed` outcome and also requires `Idempotency-Key`.
- Exact retries return the existing record. Reusing a key for a different Claim, decision, value,
  reason, group, or outcome returns a conflict.

`approve` copies the immutable candidate kind, value, and normalization. `approve_with_edit`
validates the edit against the same controlled value kind and stores it separately. Equivalent
edits are rejected so the provenance clearly distinguishes approval from a material correction.
Reject and defer decisions cannot carry an approved value. Every approval requires exact evidence.

## Conflict gate

Resolution requires every group member to have a latest approve, approve-with-edit, or reject
decision. Deferred and unreviewed members keep the group open. At least one normalized value must
be approved. A `conflicting` relation must retain exactly one approved normalized value, while a
`possibly_coexisting` relation may retain several. Dismissal is an explicit human override and
always retains its reason, actor, timestamp, and command lineage.

## Persistence and observability

Migration `20260815_0007` adds project-unique nullable command keys without rewriting legacy
reviews. Existing closed groups are data-preservingly labelled as legacy closures before the new
complete-state constraint is enabled. The closure also freezes its decision-count summary so an
exact retry returns the same result even if later reviews are appended. Review records remain PostgreSQL-immutable. Audit events
reference review/group identity and decision counts without duplicating human reasons or values.

The Claim read model derives current human status from the latest append-only review and returns
the full history. The bilingual interface places review controls and history directly under exact
evidence and places guarded closure controls inside each open conflict card.

## Verification

- domain normalization and service tests cover typed edits, evidence gates, exact replay,
  conflicting key reuse, append-only history, single-value resolution, coexistence, and dismissal;
- API/OpenAPI tests cover project-scoped review, history, and closure routes;
- migration upgrade, downgrade, and re-upgrade pass against disposable PostgreSQL;
- all PostgreSQL suites pass with database triggers and constraints enabled;
- frontend type checking, tests, production build, and Chinese desktop/English mobile browser
  smoke checks pass without console errors or horizontal overflow.

C4 does not publish a knowledge snapshot. C5 must select exact approving review IDs, calculate a
deterministic content digest, reject open conflicts and stale/non-approving decisions, and expose
immutable version history.
