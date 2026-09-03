# Contributing to GameCrafter

GameCrafter accepts focused changes that preserve evidence lineage, privacy, deterministic failure
behavior and the strict zero-paid-API local boundary.

## Before coding

1. Open an issue or short design note for a new product capability.
2. State the user problem, data entering/leaving the machine, Agent/model boundary, human gate and
   observable acceptance evidence.
3. Keep implemented behavior, local simulation and roadmap ideas explicitly separate.

Do not add cloud calls, analytics, trackers, automatic social posting, unofficial TikTok scraping
or public hosting assumptions without an approved privacy and commercial boundary change.

## Local workflow

Use the project-local environment and frozen dependency graph:

```powershell
.\scripts\setup.ps1
.\scripts\database.ps1 up
.\scripts\start.ps1
```

Run the complete local gate before opening a pull request:

```powershell
.\scripts\verify.ps1
```

Changes to database behavior require an Alembic upgrade/downgrade/upgrade test against a disposable
database whose name contains `test` or `acceptance`. User-interface changes require desktop and
mobile browser acceptance; unit tests alone are not visual evidence.

## Change rules

- Preserve source URL, immutable version, exact evidence offsets and human/Agent authorship.
- Keep security and publication policy deterministic and outside model control.
- Use typed Agent handoffs; do not add unconstrained conversational Agent loops.
- Never log prompts, credentials, cookies, uploaded documents or private evidence bodies.
- Add explicit loading, empty, failure, retry and permission-denied states.
- Update the acceptance matrix, architecture/roadmap and changelog when their claims change.
- Do not edit generated lock files by hand. Follow
  [`docs/security/reproducible-releases.md`](docs/security/reproducible-releases.md).

## Pull requests

Keep one coherent risk area per pull request. Complete the repository template with tests, privacy
impact, rollback behavior and honest exclusions. CI must pass, and dependency-update pull requests
must regenerate both hashed Python exports before merge.
