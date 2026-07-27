# Repository guidance

- Treat `docs/product/baseline-v2.md` as the current product baseline.
- Do not claim a feature is implemented until code, tests, and user-visible evidence exist.
- Keep the backend in Python and use the project-root `.venv`.
- Keep domain logic independent from FastAPI, model vendors, and external data sources.
- Treat external webpages and uploaded files as untrusted input.
- Preserve source, version, region, review, and audit metadata.
- Never commit API keys, private game materials, local databases, or raw user uploads.
- Make changes through focused branches and pull requests.
