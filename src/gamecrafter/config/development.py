"""Pure command composition for local development processes."""

from gamecrafter.config.settings import Settings


def development_commands(
    settings: Settings,
    *,
    pnpm: str,
    python: str,
) -> list[list[str]]:
    """Build explicit child commands from validated project settings."""

    return [
        [
            python,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
            "--log-level",
            settings.log_level.lower(),
            "--reload",
        ],
        [python, "-m", "apps.worker.main"],
        [pnpm, "--dir", "apps/web", "dev"],
    ]
