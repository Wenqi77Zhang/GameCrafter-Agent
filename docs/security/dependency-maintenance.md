# Dependency maintenance

GameCrafter separates automatic discovery of updates from human-controlled release changes.

## Automated coverage

Monthly Dependabot checks cover the uv Python graph, Dockerfiles, Docker Compose images and GitHub
Actions. Its pull requests remain subject to the same immutable-input contract and CI as product
changes; they are never auto-merged.

The frontend currently declares pnpm 11.9.0. GitHub's current
[supported-ecosystems table](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories)
lists pnpm through version 10, so npm-ecosystem updates are deliberately not configured until pnpm
11 is officially supported. This avoids a permanently failing automation. Frontend dependencies
are reviewed manually through `pnpm outdated` and changed only with a frozen-lock install, tests
and a production build.

## Python export gate

Dependabot may update `pyproject.toml` and `uv.lock`; the two pip-compatible exports must then be
regenerated with the documented procedure. The release contract compares the complete uv
resolution with `requirements-dev.lock`, so a stale export fails CI rather than silently shipping.

## Review checklist

- read upstream release and security notes;
- avoid combining dependency changes with feature work;
- regenerate locks rather than editing them;
- run database migration/recovery tests for ORM, validation or driver changes;
- run official-site capture tests for HTTP, browser or parser changes;
- run desktop/mobile acceptance for React, TypeScript or build-tool changes;
- rebuild production images without cache and confirm the local doctor is green.
