# M1-C C2.4a Knowledge delivery API

## Outcome

C2.4a provides the stable backend delivery boundary required by the separate Knowledge workspace.
It does not implement the C2.4b user interface, human review, conflict resolution, or snapshot
publication.

## Entity identity and correction

- The first delivery slice creates project-scoped `game` entities from a required display name and
  optional aliases.
- The server owns `canonical_key`. The first game uses the project slug, which preserves the
  `game:nte` key for the default NTE project without asking a beginner to manage internal IDs.
- Repeating an equivalent create request returns the existing active identity instead of creating a
  duplicate.
- `knowledge_entities` remains immutable. Human corrections append a
  `knowledge_entity_revisions` row containing the corrected display name, aliases, reason, actor,
  status, revision number, and timestamp.
- Archival is an append-only terminal revision. It hides the entity from the default list and blocks
  new extraction, but never deletes or relocates prior claims.
- Migration `20260815_0006` backfills one baseline revision for every existing entity and installs
  project-lineage, sequential-number, terminal-archive, and immutability triggers.

## Delivery APIs

- `GET/POST /api/projects/{project_id}/knowledge-entities`
- `PUT /api/projects/{project_id}/knowledge-entities/{entity_id}`
- `POST /api/projects/{project_id}/knowledge-entities/{entity_id}/archive`
- `GET /api/projects/{project_id}/knowledge-entities/{entity_id}/revisions`
- `GET /api/projects/{project_id}/source-versions`
- `GET /api/projects/{project_id}/knowledge-extraction-capability`
- `GET /api/projects/{project_id}/knowledge-claims` with optional subject/run filters

Source-version reads are latest-first and include historical version, provenance, digest, capture,
and normalized-text-availability fields. Candidate claims are explicitly marked
`candidate_unreviewed`; evidence contains the persisted quote and source/version metadata so a
browser never needs to re-slice Unicode text using JavaScript offsets.

## Strict zero-cost preflight

The capability read model never invokes a model. It returns one safe state:

- `provider_disabled`;
- `fixture_missing`;
- `fixture_invalid`;
- `target_mismatch`;
- `fixture_incomplete`; or
- `available` for a complete exact local replay.

The existing extraction command consumes the same preflight, so the interface cannot claim a run is
available when the command would reject it. No local fixture path, prompt, source body, response
body, or secret is returned.

## Verification

- entity create/deduplication/correction/archive/history integration tests;
- latest and historical source-version read tests;
- API and OpenAPI contract coverage;
- exact replay capability and filtered-claim tests;
- archived-subject extraction guard;
- PostgreSQL immutable revision and terminal archive coverage;
- fresh upgrade, downgrade/upgrade, and existing-entity backfill verification.
