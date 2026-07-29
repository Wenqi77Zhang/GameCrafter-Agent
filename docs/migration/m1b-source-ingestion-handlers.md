# M1-B durable source-ingestion handlers

Status: B3 implemented and locally verified on 2026-07-29.

## Implemented in B3

- registered `source.discover` and `source.capture` worker task types;
- typed, bounded payload validation with explicit quick or targeted discovery modes;
- exactly one quick-discovery listing page or up to ten targeted-history pages, with configured
  candidate limits;
- source-type and publication-window filtering without recursive crawling;
- same-project candidate resolution across separate discovery and capture runs;
- direct official-URL capture as an explicit human-triggered path;
- per-job request budgets, robots enforcement, host spacing, and concurrency gates;
- conditional ETag/Last-Modified requests and 304 version reuse;
- HTTP-first capture and adapter-approved homepage browser fallback;
- deterministic visible-text extraction that ignores executable or hidden document sections;
- bounded same-host PNG, JPEG, WebP, and GIF capture with media-type, byte, and signature checks;
- content-addressed storage of raw HTML, normalized UTF-8 text, and images;
- transactional source, version, asset-link, candidate-state, and audit-event persistence;
- initial/meaningful immutable version lineage and evidence-fingerprint no-change detection;
- explicit retry policy for timeouts, 408, 425, 429, and server failures;
- terminal handling for invalid inputs, policy/robots denial, oversize content, unsupported media,
  missing browser runtime, and cross-project or unselected candidates;
- an architecture-boundary test preventing domain/application imports of infrastructure or delivery
  frameworks.

## Human-gate semantics

Discovery and capture are different durable runs. A completed discovery run produces reviewable
candidates. B4 will let a human select one candidate and enqueue a new capture run. The repository
accepts that candidate only when it is selected and belongs to the same project. A candidate from
another project cannot be resolved even in the current local single-user release.

Direct URL import does not need a discovery candidate because submitting the URL is already the
explicit human action. The same official-host, path, robots, and resource boundaries still apply.

## Evidence-version semantics

The meaningful-evidence fingerprint includes the parser version, normalized visible text, and
captured image digests. Matching evidence reuses the existing version and emits a no-change audit
event. Changed text or images create the next immutable version and retain a link to the preceding
version. Raw HTML is stored for replay whenever a new version is created.

Image failures are best-effort and counted in version details. They do not discard otherwise valid
HTML and text evidence. External-host assets, SVG, invalid signatures, robots-denied paths, and
oversized responses are skipped rather than trusted.

## Transaction and recovery boundary

PostgreSQL owns source identity, immutable lineage, references, candidate state, and audit history.
Object storage owns bytes. Content-addressed objects are written before the database transaction so
the database never references missing bytes. If the database transaction later fails, an
unreferenced object can remain; B3 does not delete it because it may already be referenced by
another version. A future dependency-aware garbage collector must prove the object is unreferenced.

Worker retries are safe: a repeated fingerprint reuses the existing source version, and object
storage deduplicates bytes by SHA-256.

The access scheduler is process-local because B3 runs one local worker. Multi-process or remote
deployment requires a shared rate limiter; starting several workers is not a supported way to
increase crawl throughput.

## Deliberately not implemented in B3

- no API or product interface starts, selects, or monitors these tasks;
- no SSE progress stream exists;
- no browser runtime is downloaded automatically;
- no external-CDN or SVG image is captured;
- no local document or video-transcript ingestion exists;
- no claims, embeddings, conflict resolution, or human fact-review workflow exists;
- no live NTE acceptance record is committed.

These remain B4, M1.1, M1-C, and M1-D work.
