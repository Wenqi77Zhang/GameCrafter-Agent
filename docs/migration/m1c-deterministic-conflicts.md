# M1-C C3a deterministic conflict service

## Outcome

C3a turns the conflict tables reserved in C1 into an executable, explainable application service.
An explicit local command compares immutable candidate Claims, creates missing open groups and
members in one serialized transaction, records an audit event, and exposes enriched project-scoped
reads for the later conflict interface.

No model is called and no value is selected, approved, rejected, or published.

## Comparison policy

Candidates are comparable only when project, subject entity, controlled predicate, and the exact
scope fingerprint match. The scope already covers locale, region, effective time window, and game
version. A group is created only when at least two distinct normalized values exist.

Policy `claim-conflict-v1` classifies these predicates as single-valued within one exact scope:

- `game.name`;
- `release.status`;
- `release.date`;
- `genre.primary`.

Their differing values are `conflicting`. Every other controlled predicate is
`possibly_coexisting`. This deliberately avoids false automation: a game can have multiple aliases,
developers, platforms, features, locations, or compatible descriptive claims.

## Persistence and lifecycle

- a project row lock serializes reconciliation for one project;
- existing group and group-member unique keys make retries idempotent;
- every member stores the relation and a human-readable basis containing the policy version;
- an open group may receive newly extracted comparable Claims;
- a resolved or dismissed group is never silently reopened or mutated; the command reports it as
  skipped for later explicit human handling;
- every reconciliation appends `knowledge.conflicts_reconciled` with counts and policy version.

## APIs

- `POST /api/projects/{project_id}/knowledge-conflicts/reconcile`;
- `GET /api/projects/{project_id}/knowledge-conflicts` with optional `status` and
  `subject_entity_id` filters.

Reads include the current entity label, group lifecycle, distinct/member counts, relation basis,
unreviewed Claim metadata, and existing server-returned exact evidence. They do not expose source
bodies, local paths, prompts, credentials, or model response bodies.

## Verification

- unit tests pin the exclusive-predicate set and conservative fallback;
- SQLite integration covers exact grouping, duplicate normalized values, idempotent retries,
  enriched reads, audit counts, and closed-group protection;
- API and OpenAPI tests cover project-scoped reconcile and filtered reads;
- real PostgreSQL coverage proves group/member triggers and idempotent persistence.

C3b conflict visualization, C4 append-only human review commands/UI, and C5 immutable publication
remain separate milestones.
