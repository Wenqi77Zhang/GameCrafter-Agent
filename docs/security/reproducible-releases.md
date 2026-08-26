# Reproducible release policy

GameCrafter 1.0 never updates a dependency implicitly during an ordinary build.

## Enforced inputs

- `uv.lock` is the source resolution for Python.
- `requirements.lock` and `requirements-dev.lock` export exact versions and accepted artifact
  SHA-256 hashes. Production installs only the former; CI installs the latter.
- `pnpm-lock.yaml` and frozen pnpm installation control the frontend graph.
- `scripts/setup.ps1` consumes the locked Python and frontend graphs instead of resolving ranges.
- Python, Node, Nginx and pgvector container inputs use immutable image digests.
- GitHub Actions use full commit identifiers rather than movable major-version tags.

The lock files do not make old dependencies permanently safe. They make changes explicit and
reviewable. Security updates are handled as their own pull request and must pass the same database,
browser and recovery gates as application changes.

## Deliberate update procedure

From the repository environment, use the project-local uv cache and regenerate all three Python
artifacts from the same resolution:

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD ".uv-cache"
& "C:\Users\wenqi\.local\bin\uv.exe" lock --upgrade
& "C:\Users\wenqi\.local\bin\uv.exe" export --frozen --no-dev --no-emit-project --output-file requirements.lock
& "C:\Users\wenqi\.local\bin\uv.exe" export --frozen --all-extras --no-emit-project --output-file requirements-dev.lock
```

Then run the complete verification script, disposable PostgreSQL migration/recovery acceptance,
clean production container rebuild, desktop/mobile browser acceptance and GitHub CI. Do not edit a
generated lock file by hand and do not combine dependency upgrades with unrelated feature work.
