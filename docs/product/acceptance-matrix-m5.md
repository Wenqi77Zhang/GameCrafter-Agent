# GameCrafter M5 acceptance matrix

Status values are **complete**, **partial**, **deferred**, or **not applicable**. A row is complete
only when product UI, backend behavior, and automated evidence agree.

| Area | Acceptance | Status | Evidence |
| --- | --- | --- | --- |
| Journey | A new user sees the ordered Sources → Knowledge → Marketing → Create → Deliver flow and one next action | complete | `ProjectJourney.tsx`, frontend tests, Chromium desktop/mobile acceptance |
| Evidence | Official material, exact quotes, versions, reviews, conflicts, and publication lineage stay inspectable | complete | M1 tests and NTE PostgreSQL acceptance |
| Agents | Eight versioned specialists exchange typed artifacts through the durable Harness | complete | `/agents`, Agent review tests, architecture DAG |
| Trends | User-verified HTTPS observations retain source/time/region and receive deterministic normalization, dedupe, cluster, and freshness metadata | complete | `trend-processing-v1`, marketing service tests, Marketing cards |
| Topic gate | Fit exposes dimensions, rationale, risk, and exact lineage; scripts remain blocked before human approval | complete | marketing integration/API/UI tests |
| Creation | Script, evaluation, bounded revision, edit history, final approval, and Markdown/JSON export are continuous | complete | script service/API/UI tests |
| Recovery | Loading/failure/success states are visible and terminal failed jobs require an explicit audited retry | complete | database-startup guard and retry service/API/UI tests |
| Observability | Project metrics, run status/checkpoint/error, SSE events, Agent/rule versions, local token usage, and API cost are visible | complete | overview API, Journey metrics, Runs and Knowledge panels |
| Responsive UX | Main journey has no horizontal overflow at desktop and 390 px mobile widths | complete | `m5_browser_acceptance.py` screenshots and exit status |
| Packaging | One production-preview command runs migrations, DB, API, worker, object storage, and web health checks | complete | `compose.production.yaml`, `production.ps1`, container validation |
| Cost/privacy | First release uses public evidence, local storage, deterministic roles, replay/local Ollama, and no paid API | complete | settings, security docs, zero-cost acceptance |
| Live local AI | Real NTE capture runs through exact-quote Curator v5 and adversarial Reviewer 1.2 without exposing internal entity keys | complete | 2026-08-30 production capture/extraction/review record, gateway and governance tests |
| Public hosting | Anonymous internet URL | deferred | conflicts with strict zero-cost/local single-user boundary; container artifact is ready for later hosting |
| Accounts/teams/billing | Auth, tenant isolation, RBAC, billing | deferred | explicitly M6–M7, excluded from first release |
| Private GDD cloud workspace | Authenticated private document/GDD Studio | deferred | explicitly M8; needs a separately approved privacy model |

The old classroom matrix is historical and contains team/LangGraph/chat requirements that were
superseded by the confirmed personal-product baseline. They are not silently counted as complete.
