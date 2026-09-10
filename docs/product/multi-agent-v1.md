# GameCrafter constrained multi-Agent v1

Historical M15 record, with M19 execution classification corrected on 2026-09-11.
For current verification, see [real creative workflow](real-creative-workflow.md).

GameCrafter uses eight versioned specialist roles coordinated by the durable Harness. Agents exchange
typed, persisted artifacts rather than free-form conversations. Deterministic validation remains
authoritative for integrity, permissions, evidence offsets, deduplication, state transitions, and
publication gates.

| Key | Role | First-release execution |
| --- | --- | --- |
| `knowledge.source_steward` | bounded source validation and provenance capture | deterministic |
| `knowledge.curator` | evidence-bound candidate extraction | local Ollama |
| `knowledge.reviewer` | independent semantic review and risk routing | local Ollama |
| `marketing.trend_analyst` | provenance-preserving trend normalization and fit | deterministic tool |
| `marketing.campaign_strategist` | frozen evidence to a readable Chinese proposal and English hooks | local Ollama |
| `creation.script_writer` | English storyboard writing and bounded actual revision | local Ollama |
| `creation.quality_critic` | independent evidence/clarity review | local Ollama plus deterministic delivery gates |
| `design.gdd_architect` | exact-offset GDD chapters and explicit assumption separation | deterministic |

There are five model roles and three deterministic tools, not eight conversational LLM agents.
They retain typed inputs, outputs, versions and traces. Model choice is evaluated with real local
calls and negative examples; a model saying "passed" is not proof that the claims are true.

Knowledge review produces `agent_approved`, `agent_rejected`, or `needs_human`. Deterministic gates
run before the reviewer. A human confirms the reviewed knowledge pack once; only unresolved claims
require individual attention. Topic selection and final script export remain human gates.

The historical Campaign Strategist 1.1 emitted `marketing-strategy-brief-v1`. It remains a rule-only
reference, visibly separate from the M19 model recommendation. The older UI displayed
one explicit direction, recommended English topic, core message, timed content structure, approved
proof facts, trend provenance, risks, and up to two alternatives. A draft remains reviewable; an
approved brief exposes a direct transition to Script Writer. This projection alone did not close
the creative-quality gap; M19 adds actual model writing, independent checking and editable outputs.

Curator v5 receives a controlled subject type and user-confirmed display labels, but never the
internal entity key. Labels identify the review scope and cannot substitute for a public-source
quote. A malformed or unsupported candidate is discarded without being persisted; other chunks
continue. Names classified as game or character identities must occur in their exact cited quote.

Reviewer 1.2 adds an independent grammatical-subject check for character identities. A direct
clause such as `Shinku can ...` may be proposed for approval. A possessive (`Inanna's ...`) or an
attribution (`according to Sakiri`) is only a mention and is rejected or routed to human attention.
This deterministic post-model policy remains authoritative even if the local 4B model is
overconfident.

Security-sensitive account, RBAC, quota, secret, integrity, export, and deletion decisions are not
Agents. They are deterministic platform policies. This prevents a model from granting itself
permissions or weakening a privacy gate. The GDD Architect structures text but cannot approve its
own proposed design assumptions; those remain explicit human decisions.

Acceptance covers exact-target extraction reuse, controlled-predicate guidance, exact evidence,
append-only Agent review records, a batch confirmation path, eight visible/versioned Agent specs,
durable audit metadata, updated architecture DAGs, and an NTE end-to-end test. The two later
deterministic roles retain the same typed-artifact and audit boundary.

## Beginner workflow

1. In **Sources**, import one official page and wait for `succeeded`.
2. In **Knowledge**, choose the game and newest evidence version, then run extraction once.
3. When extraction succeeds and local Ollama is configured, choose **Run reviewer Agent**. The
   reviewer is a separate local-model pass; it does not see or reuse the Curator's hidden reasoning.
4. Inspect the keep/remove/needs-human totals and evidence. Removed items stay available behind the
   filtered-items toggle, so nothing is silently deleted.
5. Choose **Confirm reviewer suggestions** to record human approval/rejection for clear items.
   Review only `needs_human` or any item you want to override individually.
6. Run conflict detection and publish the immutable knowledge snapshot only after all blockers are
   resolved. Continue to Marketing and Create; topic selection and final export still require you.

Starting extraction or review twice is safe. An exact completed target is returned instead of
creating another batch, while a changed source version or prompt creates a separate auditable run.

## Live NTE acceptance record

On 2026-08-30 the production stack captured the allowlisted English NTE homepage, preserved its
normalized-text digest, and invoked local `qwen3.5:4b` over four deterministic chunks. Curator v5
persisted eight candidates with exact source offsets. Reviewer 1.2 independently reviewed all
eight, approved six, and rejected the two attribution/possessive identity errors. Provider-reported
usage was local token accounting only; paid API cost remained zero. The fixture-backed PostgreSQL
acceptance remains separate and deterministic for CI.
