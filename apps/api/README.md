# API entrypoint

The executable FastAPI entrypoint is `apps.api.main:app`. Business code lives under
`src/gamecrafter/` so it remains independent from the transport layer.
