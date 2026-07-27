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

Authentication, tenant isolation, private object storage, account export/deletion, rate limiting, and privacy terms are release gates for M6, not current M0 features.
