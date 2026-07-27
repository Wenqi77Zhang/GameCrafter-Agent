# ADR-003: PostgreSQL with full-text search and pgvector

Status: accepted; the PostgreSQL and pgvector foundation begins in M1-A.

## Context

GameCrafter needs transactional project data, evidence metadata, version and region filters, audit records, full-text retrieval, and semantic retrieval.

## Decision

Use PostgreSQL as the primary data store and combine native full-text search with pgvector. Do not add a separate vector database until scale or operational evidence justifies it.

## Consequences

- structured filters and semantic retrieval share one consistency boundary;
- local development needs PostgreSQL when M1 persistence begins;
- vector indexing and retrieval quality still require explicit evaluation;
- large raw documents remain outside relational rows behind object-storage references.

M1-A enables the `vector` extension but deliberately creates no embeddings or vector indexes.
Retrieval evaluation remains a later Knowledge Hub concern.
