# Mature local-product acceptance matrix (M9–M12)

This matrix closes the gap between “feature complete” and a product that can safely keep a small
studio's evidence and decisions for long-term local use. It extends, rather than replaces,
`acceptance-matrix-complete-local.md`.

| Gate | Required behavior | Failure behavior | Evidence |
|---|---|---|---|
| Verified recovery | Export is a versioned, restorable project archive with database IDs, typed records and content-addressed objects | reject unknown versions, corrupt hashes, missing/extra objects, duplicate entries, links, traversal, zip bombs, ID/slug conflicts; write no partial project | SQLite round trip, corruption test, PostgreSQL migration and production acceptance |
| Recovery ownership | Restored projects belong to the signed-in user and their default local team; archived tenant IDs are never trusted | quota is checked before restore; auth-disabled restore remains explicitly single-user | API/RBAC tests and account recovery UI |
| Team governance | Owner can change non-owner roles and atomically transfer the team plus every team project | owner cannot demote themselves; inactive/non-members cannot receive ownership; prior roles and actor IDs remain audited | service/API tests and owner-only controls |
| Browser session security | unsafe cookie-authenticated requests require the exact configured Origin | missing or foreign Origin is denied; public login/bootstrap remains available without a session | CSRF regression test |
| Login abuse resistance | failures are throttled across restarts using only a normalized-email SHA-256 | fifth failure blocks the identifier for 15 minutes; response stays generic; successful login clears failures | persistent throttle test and migration 0017 |
| Browser hardening | API and production web responses prevent framing, MIME sniffing, broad referrers and unneeded device permissions; CSP limits content origins | unsafe embedding and unexpected active content are browser-blocked | header integration test and production smoke |
| Accessible operation | active workspace is programmatically exposed, keyboard focus is visible, status messages are announced, destructive controls are disabled until confirmed | mouse-only use is not required for core journeys | Vitest, Chromium desktop/mobile and manual keyboard check |
| Honest product boundary | strict zero-paid-API local product is explicit; public hosting, payment, auto-posting, video rendering, OCR and TikTok scraping are not claimed | unavailable capabilities are documented as exclusions, never simulated | README, roadmap, architecture and redundancy audit |

## Release definition

Mature local release means one user or a small trusted team can install, recover, operate, audit,
and remove their GameCrafter data on a machine they control. It does **not** mean an unattended
public SaaS: that would need a separate threat model, managed secrets/backups, legal/privacy work,
email delivery, billing and production incident operations.

The release gate is green only after formatting/lint, all Python and frontend tests, Alembic head,
disposable PostgreSQL acceptance, production Compose health, and desktop/mobile Chromium acceptance
pass against the same commit.
