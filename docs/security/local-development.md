# Local-development security baseline

The first release is local and single-user. That reduces but does not remove data risk.

## Rules

- keep keys in `.env`; commit only `.env.example`;
- do not import real commercial secrets during the public-game validation phase;
- treat websites, transcripts, model outputs, and uploads as untrusted data;
- show which content will leave the machine before a model call;
- validate URL schemes, hosts, redirects, response size, and file types before ingestion;
- redact secrets and unnecessary private content from logs;
- preserve source and human-review metadata;
- support deletion of sources, snapshots, runs, and local uploads;
- do not scrape authenticated or disallowed sources.
- bind the development database port to `127.0.0.1`, not all network interfaces;
- keep the Docker volume, database URL, local snapshots, and raw data outside Git;
- expose detailed dependency failures in server logs only; `/ready` returns a safe generic error.

## M1-B official-site access controls

- only HTTPS URLs on exact approved official hostnames and explicitly listed paths are accepted;
- embedded credentials, non-default ports, fragments, dot segments, backslashes, control
  characters, and tracking parameters are rejected or removed before identity comparison;
- all resolved addresses must be public, and every redirect is authorized again before following;
- HTTP responses are constrained by redirect count, timeout, media type, and decompressed byte size;
- cookies are cleared between HTTP requests and environment proxy settings are not inherited;
- the browser fallback is opt-in per page pattern, uses a fresh isolated context, and blocks
  downloads, service workers, popups, dialogs, cross-host resource requests, and excessive
  same-host subresources;
- request-count limits, per-host/global concurrency, and minimum intervals are enforced inside the
  current single B3 worker process; a larger crawl delay declared by robots rules raises the host
  interval. Multi-process deployment requires a shared rate limiter before it is supported;
- robots rules are fetched through the same URL and response controls, cached within the job, and
  conservatively enforced before page or image access;
- only same-host PNG, JPEG, WebP, and GIF candidates are accepted; each image has a byte limit and
  must match its declared format signature. SVG and external CDN assets are not captured in B3;
- captured website content remains untrusted evidence and cannot directly choose tools, prompts, or
  final marketing claims.

Playwright is an exceptional fallback rather than the default capture mechanism. The Python package
is installed with normal project dependencies, while its browser binary is an explicit local
operation (`.\scripts\browser.ps1 install`) to avoid a hidden large download.

DNS validation occurs immediately before each adapter request, but the current client does not pin
the validated address to the connection. Exact official-host allowlists substantially reduce the
exposure, while connection-level DNS pinning remains a hardening item before remote or multi-tenant
deployment.

PostgreSQL and local object storage do not share one transaction. A failed database transaction can
leave an unreferenced content-addressed object, but cannot expose a partial source version. A later
garbage-collection command must delete only objects proven unreferenced by `source_assets`.

The M1-A database password is a local-only development placeholder. It must be replaced before any
shared or remote deployment.

Authentication, tenant isolation, private object storage, account export/deletion, rate limiting,
and privacy terms are release gates for M6, not current M1-B features.
