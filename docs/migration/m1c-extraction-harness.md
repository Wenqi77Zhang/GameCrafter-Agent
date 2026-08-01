# M1-C C2.2 deterministic extraction Harness

## Outcome

C2.2 turns the C2.1 gateway contracts into a runnable, strictly offline extraction core. It adds:

- versioned deterministic chunking with a 4,000-character maximum and 400-character overlap;
- exact Unicode code-point offsets and SHA-256-bound chunk identities;
- sequential request orchestration through the provider-neutral `ModelGateway`;
- whole-document fail-closed behavior and safe error summaries;
- request/result fingerprint verification;
- deterministic overlap deduplication and aggregate usage accounting;
- an invocation manifest containing only bounded trace metadata;
- a strict source-attributed offline fixture loader;
- a minimal English NTE official-homepage replay with network-blocking tests.

## Why this is not ReAct or a multi-Agent swarm

Knowledge extraction has a fixed goal, fixed input, fixed schema, and no research-tool decision.
Allowing agents to converse or improvise would make evidence offsets, retries, and replay harder to
audit. C2.2 therefore uses one Knowledge Curator specialist inside deterministic orchestration.
Later research workflows may use local bounded ReAct where tool selection is genuinely required.

## Evidence and offset policy

The chunker never changes the normalized source text. It prefers paragraph, newline, and sentence
boundaries, but hard-splits oversized spans. The overlap is exact and bounded. All offsets are
Python Unicode code-point indices. A later web interface must render server-returned evidence
quotes and context rather than applying these offsets directly to JavaScript UTF-16 strings.

Every gateway result must match the request fingerprint for that exact source version, subject,
chunk, offset, locale, region, prompt, and schema. The strict decoder converts chunk-relative
evidence to absolute source offsets before the Harness receives it.

## NTE replay truthfulness

`fixtures/nte/official-homepage-en-v1.json` contains a small description captured from
`https://nte.perfectworld.com/en/main.html` on 2026-08-01. It records a text digest and exact request
fingerprint. It is an offline test snapshot of public official-site metadata, not an internal GDD,
a claim that the live page is unchanged, or a real model response. Token usage is zero.

## Security and privacy

- no model SDK or live provider client is installed or constructed;
- tests replace socket connection attempts with a hard failure;
- fixtures reject unknown fields, stale fingerprints, and altered source text;
- Harness errors expose chunk number and safe error type, not source text or provider messages;
- no source URL, local path, raw HTML, image, secret, or unrelated log is sent to a model.

## Deliberately deferred

- `knowledge.extract` durable jobs and checkpoints;
- model-invocation and candidate-claim persistence;
- source-version/object-storage loading in an application command;
- extraction preflight and HTTP APIs;
- the bilingual extraction workbench;
- deterministic conflict processing, review actions, and snapshot publication;
- any live model call or paid API use.

These belong to C3 and later slices.
