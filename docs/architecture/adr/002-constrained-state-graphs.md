# ADR-002: Constrained state graphs instead of an autonomous agent swarm

Status: accepted.

## Context

The product requires evidence, resumable human decisions, bounded costs, visible failures, and reproducible versions. A free-form supervisor and autonomous subagents would make those properties harder to guarantee.

## Decision

Use deterministic LangGraph state graphs with specialist nodes, explicit schemas, bounded tool use, checkpoints, evaluator–optimizer limits, and human approval gates. Run every graph inside an Agent Harness that enforces state validation, idempotency, budgets, permissions, timeouts, retries, tracing, model-egress policy, and resumable human pauses.

Research nodes may use a bounded `Perceive → Reason → Act → Evaluate` cycle. ReAct is allowed only where tools are genuinely required and must use an allowlist, timeout, call limit, and budget. ReWOO is not a core orchestration pattern because the state graph is the inspectable global plan.

`Learn` is an offline, human-governed release process rather than live self-modification. Production runs cannot rewrite prompts, skills, rules, policies, or tool permissions. Approved feedback enters a versioned evaluation set, and tested changes ship as new, reversible versions.

ToolProvider implementations begin in-process. MCP may be added behind that port for cross-application reuse or independently managed permissions, but it does not replace the state graph or Harness.

## Consequences

- product state can be explained and rendered in the UI;
- failures and decisions can be replayed;
- low-quality outputs and exhausted retry budgets remain explicit human exceptions;
- offline learning preserves rollback, attribution, and behavior stability;
- some open-ended flexibility is intentionally sacrificed;
- adding a node requires an explicit contract and state transition.
