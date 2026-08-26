# M5 portfolio-ready local release

M5 turns the completed M0–M4 capability set into a product that a new user can navigate and that a
reviewer can run, inspect, recover, and deploy locally without paid infrastructure.

## Implemented

- `GET /api/projects/{project_id}/overview` derives five stage states and honest project metrics
  from persisted evidence, snapshots, trend observations, topic decisions, script versions,
  approvals, exports, and workflow runs.
- The web workspace renders the same five stages, shows the single next action, links every stage to
  its real workspace, and keeps simplified Chinese as the default.
- `trend-processing-v1` derives normalized titles, SHA-256 fingerprints, exact-duplicate lineage,
  related-event clusters, cluster sizes, and freshness from immutable manual observations. The
  transformation is deterministic and visible; it is not described as a live TikTok connector.
- `POST /api/runs/{run_id}/retry` requeues failed jobs only after `needs_attention`, resets the
  bounded attempt budget, preserves the run ID/history, and appends an idempotent human retry event.
- `compose.production.yaml` builds and runs migrations, PostgreSQL/pgvector, API, worker, Nginx web,
  object storage, and health checks. The replay provider keeps the preview at zero API cost.
- `scripts/m5_browser_acceptance.py` verifies the real page in Chromium at desktop and mobile
  widths, including the guided workflow, console safety, and horizontal overflow.

## Failure case

A stopped database is reported before business controls render. A terminal worker failure shows its
safe error and can be requeued only by an explicit user command after the cause is addressed. The
original failure and the retry both remain in the audit timeline.

## Honest boundary

M5 is a local production preview, not a hosted multi-user SaaS. Authentication, tenant isolation,
billing, team roles, private online uploads, and GDD Studio remain M6–M8 roadmap work. Adding them
requires a new approved privacy and commercialization baseline.

