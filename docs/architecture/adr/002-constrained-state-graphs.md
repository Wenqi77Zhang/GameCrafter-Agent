# ADR-002: Constrained state graphs instead of an autonomous agent swarm

Status: accepted.

## Context

The product requires evidence, resumable human decisions, bounded costs, visible failures, and reproducible versions. A free-form supervisor and autonomous subagents would make those properties harder to guarantee.

## Decision

Use deterministic LangGraph state graphs with specialist nodes, explicit schemas, bounded tool use, checkpoints, evaluator–optimizer limits, and human approval gates.

ReAct is allowed only in research nodes with a whitelist, timeout, call limit, and budget. ReWOO is not a core orchestration pattern.

## Consequences

- product state can be explained and rendered in the UI;
- failures and decisions can be replayed;
- some open-ended flexibility is intentionally sacrificed;
- adding a node requires an explicit contract and state transition.
