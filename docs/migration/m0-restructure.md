# M0 repository restructure

## Source state

The repository contained three commits, a conceptual README, a UTF-16 `pip freeze`, and one-line placeholders for optimizer, planner, researcher, state, workflow, search, and entrypoint modules.

No executable business implementation existed, so M0 does not need a compatibility layer.

## Migration

- preserve the original commits and MIT License;
- archive the one-line placeholder intent under `legacy/`;
- replace the requirements freeze with direct dependencies in `pyproject.toml`;
- use a project-root `.venv` instead of Conda-specific editor settings;
- introduce separate API, web, domain, application, agent, and infrastructure boundaries;
- add health endpoints, a status UI, tests, scripts, CI, ADRs, and corrected README claims;
- update both the product workflow DAG and software architecture DAG.

## Scope boundary

M0 proves that the project can start, communicate, test, and build. It does not claim to implement ingestion, RAG, models, agents, trend retrieval, persistence, accounts, or billing.
