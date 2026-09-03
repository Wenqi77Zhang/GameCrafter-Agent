# M8-local completion release

This release completes the previously deferred local-product capabilities without claiming paid
cloud infrastructure, a payment processor, or autonomous social-platform publishing.

## Data migrations

- `20260826_0013` expands immutable evidence to private UTF-8 documents, transcripts, and owned
  GDD files with `local_upload` provenance and a `raw_document` asset role.
- `20260826_0014` adds source-bound GDD documents, exact-offset chapters, separately reviewed
  assumptions, and immutable revision manifests.
- `20260826_0015` adds local users, opaque session digests, team tenants, four-role memberships,
  expiring invitation digests, and optional project ownership/team boundaries.
- `20260826_0016` adds account/team security audit events without raw passwords, invitation tokens,
  private content, or unhashed invited-email values.

Existing projects are intentionally left without an owner during migration. When account mode is
enabled, the one-time local-owner bootstrap transaction creates the personal team and assigns all
legacy unowned projects. This avoids manufacturing credentials or a hidden default password.

## Runtime compatibility

- Developer mode remains passwordless unless `GAMECRAFTER_AUTH_ENABLED=true` is set.
- The production-preview composition stays beginner-safe in single-machine mode by default. Set
  `GAMECRAFTER_AUTH_ENABLED=true` before startup to enable the owner-creation screen for sharing.
- Its loopback HTTP cookie is intentionally not marked `Secure`; any real TLS deployment must set
  `GAMECRAFTER_AUTH_COOKIE_SECURE=true`.
- TikTok remains an explicit verified-manual source. Google News RSS/GDELT are live no-key public
  inputs; YouTube uses an optional locally stored official API key and free quota.

## Safety boundaries

- Local private content never enters the public trend connectors and is not written into audit
  payloads.
- Project export includes private bytes by explicit owner action and declares that fact in its
  manifest.
- Project deletion requires `DELETE <project-slug>`, removes reachable rows in dependency order,
  and removes only content objects that have no remaining references.
- Account deletion is blocked until owned projects and shared-team ownership are resolved.
- RBAC is deterministic middleware/database policy; no Agent can grant, revoke, or bypass access.
- Project-scoped run URLs resolve back to their owning project before every read or retry; complete
  project export is owner-only, while review/publication commands require reviewer authority.
- When accounts are enabled, human project events record the authenticated user ID instead of a
  shared local-user label, preserving accountable multi-user audit lineage.
