# GameCrafter constrained multi-Agent v1

Status: implemented and acceptance-tested on 2026-08-21.

GameCrafter uses six versioned specialist roles coordinated by the durable Harness. Agents exchange
typed, persisted artifacts rather than free-form conversations. Deterministic validation remains
authoritative for integrity, permissions, evidence offsets, deduplication, state transitions, and
publication gates.

| Key | Role | First-release execution |
| --- | --- | --- |
| `knowledge.curator` | evidence-bound candidate extraction | local Ollama |
| `knowledge.reviewer` | independent semantic review and risk routing | local Ollama |
| `marketing.trend_analyst` | verified trend evidence analysis | deterministic |
| `marketing.campaign_strategist` | frozen knowledge/trend topic strategy | deterministic |
| `creation.script_writer` | structured TikTok script generation | deterministic |
| `creation.quality_critic` | quality, evidence, format, and compliance evaluation | deterministic |

The first release is strictly zero API cost. A deterministic role is still an explicit specialist
node with typed inputs, outputs, version, trace, and responsibility; it is not presented as a model
call. Later model upgrades must retain the same contracts and pass offline evaluation before release.

Knowledge review produces `agent_approved`, `agent_rejected`, or `needs_human`. Deterministic gates
run before the reviewer. A human confirms the reviewed knowledge pack once; only unresolved claims
require individual attention. Topic selection and final script export remain human gates.

Acceptance covers exact-target extraction reuse, controlled-predicate guidance, exact evidence,
append-only Agent review records, a batch confirmation path, six visible/versioned Agent specs,
durable audit metadata, updated architecture DAGs, and an NTE end-to-end test.

## Beginner workflow

1. In **Sources**, import one official page and wait for `succeeded`.
2. In **Knowledge**, choose the game and newest evidence version, then run extraction once.
3. When extraction succeeds, choose **Run reviewer Agent**. The reviewer is a separate local-model
   pass; it does not see or reuse the Curator's hidden reasoning.
4. Inspect the keep/remove/needs-human totals and evidence. Removed items stay available behind the
   filtered-items toggle, so nothing is silently deleted.
5. Choose **Confirm reviewer suggestions** to record human approval/rejection for clear items.
   Review only `needs_human` or any item you want to override individually.
6. Run conflict detection and publish the immutable knowledge snapshot only after all blockers are
   resolved. Continue to Marketing and Create; topic selection and final export still require you.

Starting extraction or review twice is safe. An exact completed target is returned instead of
creating another batch, while a changed source version or prompt creates a separate auditable run.
