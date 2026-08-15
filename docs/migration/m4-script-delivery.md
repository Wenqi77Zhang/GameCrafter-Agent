# M4 evidence-bound script delivery

M4 closes the first local end-to-end product slice from a published game-knowledge snapshot and a
human-approved trend topic to an approved, downloadable English TikTok script.

## Runtime pattern

The first release uses two constrained specialist steps rather than five chatting Agents:

1. `tiktok-template-v1` deterministically composes the approved topic and snapshot facts into a
   timestamped script with knowledge and trend IDs on every relevant section.
2. `script-quality-v1` deterministically scores timeline, hook, evidence, CTA, TikTok structure,
   and schema/safety. It never edits state itself.

The user may request an automatic revision only after the latest version fails. The run freezes a
zero-to-five revision budget (two by default), so the evaluator-optimizer loop cannot run away.
Human edits create new immutable versions. A human must finally approve the exact passing version.

## Data and privacy

Migration `20260815_0010` creates immutable script runs, versions, evaluations, final reviews, and
export receipts. PostgreSQL insert triggers require one project, task, approved candidate/review,
snapshot, version, evaluation, and final approval chain. Update/delete triggers protect the audit
record. Canonical JSON digests make silent content changes detectable.

The structured editor accepts at most 64 KiB and an exact schema. It rejects unknown top-level or
section fields, discontinuous timelines, changed task duration, and knowledge/trend IDs outside the
frozen run. Export contains only approved script content and reference IDs; it excludes raw source
bodies, credentials, object paths, model prompts, and provider responses.

## Honest capability boundary

Generation and evaluation use no model SDK, provider API, token budget, live trend connector, or
unauthorized scrape. Output is deterministic template copy, not represented as AI-generated prose.
The model gateway remains available for a future opt-in capability behind the existing zero-cost
and egress boundaries, without changing M4 lineage contracts.

## Verification gates

- service tests cover generation, failed human edits, bounded revision, final approval, and export;
- API and OpenAPI tests cover the complete command surface and mandatory idempotency headers;
- migration upgrade/downgrade/upgrade runs against PostgreSQL;
- PostgreSQL tests cover cross-lineage rejection and immutable records;
- frontend tests and production build cover the Simplified-Chinese-default Create workspace;
- desktop Chinese and mobile English browser smoke tests check the complete rendered workflow,
  console errors, and horizontal overflow.
