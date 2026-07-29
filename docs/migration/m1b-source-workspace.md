# M1-B source workspace, commands, and run events

Status: B4 implemented and locally verified on 2026-07-29.

## Implemented in B4

- project creation and project-scoped source, candidate, and run queries;
- bounded quick/targeted discovery commands and explicit direct-URL import;
- atomic human candidate selection plus capture-run enqueue;
- required idempotency keys with conflicting-reuse rejection;
- append-only run-event SSE with `Last-Event-ID` recovery and terminal closure;
- a responsive Sources/Runs workspace that defaults to Simplified Chinese and remembers an
  optional English selection;
- NTE global English, Simplified Chinese, Japanese, and mainland-China quick profiles;
- targeted official listing selection, category, date window, page count, and candidate limit;
- candidate provenance and status, evidence-version/asset counts, durable run checkpoints, and
  visible failure details;
- an explicit product notice that public official evidence is not an internal GDD.

## Human and safety boundaries

Discovery never triggers capture. A candidate must still be in `discovered` state when the API
atomically marks it `selected` and creates a separate capture job. A repeated network request with
the same idempotency key returns the existing run only when task and payload match; reuse for a
different command returns a conflict.

The source adapters and worker remain the enforcement point for official host/path allowlists,
robots policy, request budgets, redirects, response sizes, and browser fallback. The UI does not
weaken those controls. SSE exposes redacted audit payloads and identifiers, not captured HTML,
normalized page text, object-storage paths, credentials, or database details.

## Recovery behavior

The browser reconnects to a selected run using `EventSource`. Each audit event has a durable event
identifier; a reconnect sends `Last-Event-ID`, and the API resumes after that event. The stream
closes after a terminal run is drained. Runs in `needs_attention` retain their checkpoint, stable
error code, and safe error detail for human diagnosis.

## Deliberately not implemented in B4

- no claims, embeddings, confidence scoring, conflict resolution, or fact approval;
- no live NTE website capture is represented as completed acceptance evidence;
- no local documents, video transcripts, trend data, models, or marketing scripts;
- no authentication, remote private upload, scheduled crawl, or multi-user collaboration;
- no automatic browser-runtime installation.

These remain M1-C, M1-D, M1.1, M2–M4, and later product milestones.
