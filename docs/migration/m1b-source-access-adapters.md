# M1-B controlled source access and NTE adapters

Status: B2 implemented and locally verified on 2026-07-29.

## Implemented in B2

- exact official hostname and path rules for the NTE global and mainland websites;
- stable HTTPS URL normalization for evidence identity;
- public-IP DNS validation and redirect-by-redirect policy checks;
- bounded request-count and validated scheduling-policy contracts;
- bounded HTML metadata parsing and robots-rule parsing;
- an HTTP-first `PageFetcher` implementation with timeout, redirect, media-type, status, and
  decompressed-size limits;
- a controlled Playwright fallback limited to approved homepage paths, with an isolated browser
  context, cross-host resource blocking, and a same-host subresource limit;
- deterministic global and mainland NTE `SiteAdapter` implementations;
- English, Simplified Chinese, Japanese, and mainland Chinese locale/region metadata;
- direct homepage/article adaptation and listing-page discovery candidates;
- explicit classification reasons and non-factual URL-date family signals;
- configuration examples and an explicit browser-runtime status/install helper.

## Access strategy

HTTP is always attempted first because it is smaller, faster, easier to test, and has a narrower
attack surface. Playwright exists for an approved homepage whose useful links or metadata are
created only after JavaScript runs. It is not a generic bypass for a failed request or a broad web
crawler.

The allowlist is intentionally structural. It authorizes only known NTE page shapes and exact
official hosts, not arbitrary subdomains or user-supplied websites. Assets may come only from the
same approved host. This reduces SSRF and supply-chain exposure while keeping the dynamic official
homepage viable.

## Metadata and evidence rules

A listing page is a discovery input, not final evidence. Each discovered article receives a
canonical URL, site, locale, region, source type, official raw category, and human-readable
classification basis. Dates visible in link text may become candidate publication dates. Dates
embedded only in URL paths are retained as grouping signals and are never asserted as publication
facts.

These public pages remain public evidence, not an internal GDD. B2 does not extract claims or make
facts eligible for marketing output.

## Deliberately not implemented in B2

- no live job handler fetches robots rules, schedules requests, or writes source versions;
- no API starts discovery or capture;
- no progress stream or Sources/Runs interface exists;
- no images or linked assets are captured;
- no browser binary is downloaded automatically;
- no real NTE page is persisted as acceptance evidence;
- no claims, embeddings, conflict resolution, or human fact-review workflow exists.

Those capabilities belong to B3, B4, M1-C, and M1-D respectively. The existing concurrency and
minimum-interval settings become operational only in the B3 scheduler.

Follow-up: B3 now registers the discovery/capture handlers and enforces robots rules, request
budgets, host spacing, and concurrency. This document remains the historical B2 boundary.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pytest
.\scripts\browser.ps1 status
```

The browser package can be installed only when a JavaScript-rendered acceptance test is required:

```powershell
.\scripts\browser.ps1 install
```
