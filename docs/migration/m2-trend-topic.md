# M2/M3 traceable trends and human topic approval

This slice connects an approved knowledge snapshot to a marketing topic without paid APIs,
unauthorized scraping, or hidden model judgment.

## M2 authorized-source input

The first release uses human-verified input: the user opens a public trend page they are authorized
to view, then records the HTTPS source URL, observation time and timezone, region, signal type,
title, keywords, optional metric, and verification note. The record is immutable and idempotent.
It is labelled as a manual observation that GameCrafter did not independently verify.

Invalid URLs, embedded credentials, naive timestamps, negative metrics, incomplete metric pairs,
oversized text, unsupported signal types, and conflicting command-key reuse fail before persistence.

## M3 deterministic fit and human gate

A marketing task freezes one published knowledge snapshot and the platform, markets, audience,
goal, output language, and duration. `trend-fit-v1` creates one immutable candidate per task/signal
pair and assigns up to 25 points each for freshness, market alignment, source completeness, and
lexical overlap with approved snapshot members. It stores each dimension, matched member IDs,
angle, hook, rationale, risk codes, and rule version. No model is invoked.

Topic reviews are append-only `approve`, `reject`, or `defer` decisions with a bounded reason,
reviewer, time, and idempotency key. A task cannot have two current approved topics; changing the
selection requires an explicit later rejection followed by a new approval.

## Persistence and verification

Migration `20260815_0009` adds marketing tasks, trend signals, topic candidates, and topic reviews.
PostgreSQL triggers enforce cross-project lineage and immutability. Verification covers service and
API behavior, OpenAPI paths, real PostgreSQL publication-to-topic flow, migration downgrade/upgrade,
mutation rejection, frontend type checking/tests/build, and Chinese desktop/English mobile browser
smoke checks without console errors or horizontal overflow.

M2/M3 do not generate scripts. M4 must consume the exact task and currently approved topic, freeze
generation/evaluation rules, use a bounded revision loop, preserve versions, and require final human
approval before export.
