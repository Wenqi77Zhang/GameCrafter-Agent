# M1-C reviewable knowledge contracts

Status: C1 implemented and locally verified on 2026-07-29.

## Implemented in C1

- controlled entity types and fact predicates for the first NTE knowledge slice;
- typed candidate-claim values with mandatory exact evidence spans;
- project-scoped entity, immutable claim, evidence, review, conflict, and snapshot records;
- append-only human decisions that preserve the model value and any approved edit separately;
- region, locale, effective-time, game-version, model, prompt, and schema provenance;
- deterministic value and scope fingerprints reserved for C3 comparison logic;
- PostgreSQL guards that prevent approval without evidence;
- PostgreSQL guards that prevent claims, evidence, and conflict records from crossing project
  boundaries or mismatching claim scope;
- PostgreSQL guards that prevent unresolved conflict members from entering a snapshot;
- PostgreSQL guards that make entities, claims, evidence, reviews, snapshots, and snapshot
  membership immutable after creation;
- exact review lineage from every snapshot member to one approving human decision.

## Why claims and reviews are separate

A model-produced claim is evidence-bound input to review, not a fact. It is never overwritten.
Approval, approval with an edit, rejection, and deferral are append-only review records. An
approving review stores the exact approved value, so a later decision cannot change the meaning of
an already published snapshot.

This design supports honest attribution:

- model output remains inspectable;
- a human edit remains attributable to the reviewer;
- source evidence remains attributable to its immutable source version;
- a marketing run can later reference one frozen snapshot rather than mutable current data.

## PostgreSQL publication gates

Database triggers provide a last line of defense in addition to future application services:

1. an approving review must belong to the same project as its claim;
2. an approving review requires at least one evidence span;
3. a claim must share its project with its subject entity and optional extraction run;
4. an evidence span must share its project with both its claim and source version;
5. a conflict group and each member must match the claim's project, subject, predicate, and scope;
6. a snapshot, claim, and approving review must share one project and claim lineage;
7. a claim in an open conflict group cannot become a snapshot member;
8. published lineage records cannot be updated or deleted.

C4 will add an atomic publication service that also prevents empty snapshots and reports all
blocking reasons before attempting the transaction.

## Deliberately not implemented in C1

- no model SDK or real model call;
- no prompt, text chunker, claim extractor, or ModelGateway implementation;
- no deterministic conflict classifier;
- no review API or Knowledge Review interface;
- no snapshot publication command;
- no embeddings or retrieval;
- no live NTE fact extraction or accepted knowledge snapshot.

These remain C2 through C5 and M1-D work.
