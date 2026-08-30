# Changelog

## Unreleased

- Production Compose now defaults to the loopback-only local Ollama path and probes both the
  runtime and exact configured model before extraction or Agent review can be queued.
- Knowledge Curator prompt v5 sends only the controlled subject type plus user-confirmed display
  labels, never the internal entity key; exact evidence remains authoritative.
- Invalid local-model candidates are discarded per candidate so one weak page segment cannot stop
  later valid segments, while fabricated game and character names are blocked unless they occur in
  the cited quote.
- Knowledge Reviewer 1.2 rejects possessive and attribution-only character mentions such as
  `Inanna's` and `according to Sakiri` instead of approving them as character identities.
- The live NTE English homepage path was exercised through capture, four local-model chunks,
  eight persisted candidates, and independent review: six approved and two rejected, at zero API
  cost. The committed replay remains the deterministic offline CI path.
- The API container installs locked dependencies before copying application source, allowing later
  code-only rebuilds to reuse the dependency layer.

## 1.0.0 - 2026-08-27

- Complete local-first NTE evidence-to-English-TikTok marketing workflow.
- Eight constrained specialist roles with durable typed handoffs and independent review.
- Verified project recovery, optional local identity/RBAC, team governance and structured GDD.
- Persistent worker/queue diagnosis, request correlation and desktop/mobile recovery UX.
- One-command production startup with readiness waiting and a read-only Chinese local doctor.
- Hashed Python locks, frozen frontend graph and immutable build/CI inputs.
- Private vulnerability-reporting guidance, contribution rules and supported dependency automation.
- Patched the transitive `nanoid` development dependency to 3.3.18 for CVE-2026-67213.
- Beginner-first Chinese workspace with one visible current task, collapsed diagnostics, a direct
  NTE homepage action and a non-wrapping mobile navigation rail.

Public SaaS hosting, billing, automatic TikTok posting, video rendering, OCR and unofficial TikTok
scraping are not part of this zero-paid-API local release.
