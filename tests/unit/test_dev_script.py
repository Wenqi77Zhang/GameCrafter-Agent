from gamecrafter.config.development import development_commands
from gamecrafter.config.settings import Settings


def test_development_commands_use_validated_server_settings() -> None:
    settings = Settings(
        _env_file=None,
        api_host="0.0.0.0",
        api_port=8123,
        log_level="DEBUG",
    )

    commands = development_commands(settings, pnpm="pnpm.cmd", python="python.exe")

    assert commands[0] == [
        "python.exe",
        "-m",
        "uvicorn",
        "apps.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8123",
        "--log-level",
        "debug",
        "--reload",
    ]
    assert commands[1] == ["pnpm.cmd", "--dir", "apps/web", "dev"]
