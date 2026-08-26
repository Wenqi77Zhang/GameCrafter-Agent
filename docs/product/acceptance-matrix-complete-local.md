# Complete local-product acceptance matrix

This matrix is the change-control source for the post-M5 completion pass. A row is complete only
when the implementation, automated evidence, failure behavior, privacy boundary, and user-facing
status all agree. “Zero cost” means no paid API or hosted-service dependency; it does not claim
that public Internet hosting, electricity, or optional hardware has no cost.

| Capability | Required behavior | Failure / safety behavior | Verification |
|---|---|---|---|
| Official game sources | NTE global/mainland discovery, explicit selection, immutable capture, provenance | allowlisted hosts, bounded fetches, visible retry/attention state | source unit, integration, PostgreSQL and browser tests |
| Local documents | TXT, Markdown, VTT transcript and user-owned GDD become private immutable evidence | UTF-8 text only, bounded size, never sent to a public model, content omitted from audit | local-source service/API/UI tests |
| Public trends | live no-key news/GDELT plus optional official YouTube free quota; TikTok remains verified manual input | bounded response/time/range, fixed hosts, secret redaction, no popularity claims from search order | connector parsing/API/UI tests and live smoke |
| Knowledge | exact evidence spans, conflicts, independent Agent pre-review, human publication gate | unsupported claims fail closed; no claim may publish without evidence and review | deterministic, PostgreSQL and browser acceptance |
| Multi-source synthesis | approved snapshot facts are grouped across exact source identities, disclosing corroborated and single-source claims | display-only deterministic rule creates no new fact and never hides single-source risk | snapshot UI test and `multi-source-synthesis-v1` disclosure |
| Marketing | normalized/deduplicated trends, snapshot-bound fit, risks, topic decision | source/time/region remain visible; uncertain fit is disclosed | marketing service/API/UI tests |
| Creation | evidence-bound English TikTok script, evaluation, bounded revision, versions, final approval, Markdown/JSON export | no export before approval; automatic loops are capped | script service/API/UI tests |
| Individual workspace | local identity, project isolation, private storage, portable export, explicit deletion, bounded usage | passwords are memory-hard hashed; opaque sessions; destructive action requires typed confirmation | security/API isolation and export tests |
| Team workspace | owner/editor/reviewer/viewer roles, invitation, revocation, approval authority and audit | default deny; revoked membership loses access immediately; no payment processor is implied | RBAC matrix and revocation tests |
| GDD Studio | source-version-bound chapters, exact offsets, explicit assumptions, immutable revisions, shared approved knowledge | assumptions never masquerade as sourced facts; history is append-only | parser/service/API/UI tests |
| Product UX | Simplified Chinese default, English switch, one visible next action, responsive desktop/mobile | errors are actionable; unavailable capabilities are not rendered as healthy | TypeScript, Vitest and Chromium acceptance |
| Operations | one-command local production stack, migrations, health/readiness, worker observability, redacted logs | readiness distinguishes database/model/data availability; secrets and private content are not logged | full verify, production smoke and security review |

## Intentional non-features

- No TikTok scraping or simulated TikTok API connection.
- No paid cloud model, hosted vector database, payment processor, or “free forever” hosting claim.
- No autonomous publication to a social platform; final export remains an accountable human gate.
- No unrestricted Agent-to-Agent chat. The Harness uses typed artifacts, bounded tools, durable
  checkpoints, and independent review.
- No duplicate RAG stack before approved knowledge demonstrates a retrieval need.

## Final release gate

The branch is not ready for user acceptance until the complete automated suite, disposable
PostgreSQL acceptance, production-container smoke, desktop/mobile browser smoke, requirements
audit, redundancy audit, and documentation consistency checks all pass.
