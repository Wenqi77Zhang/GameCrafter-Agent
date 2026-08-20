import pytest
from pydantic import ValidationError

from gamecrafter.config.settings import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.api_host == "127.0.0.1"
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert "gamecrafter_local" not in str(settings.database_url)
    assert settings.object_storage_path.as_posix() == "data/objects"
    assert settings.source_max_concurrency_per_host == 1
    assert settings.source_image_max_bytes == 5 * 1024 * 1024
    assert settings.source_max_images_per_page == 8
    assert settings.source_global_max_concurrency == 3
    assert settings.source_quick_candidate_limit == 30
    assert settings.source_targeted_candidate_limit == 100
    assert settings.worker_id == "local-worker"
    assert settings.model_provider == "disabled"
    assert settings.model_replay_fixture_path is None
    assert str(settings.ollama_base_url) == "http://127.0.0.1:11434/"
    assert settings.ollama_model == "qwen3.5:4b"
    assert settings.knowledge_document_max_bytes == 2 * 1024 * 1024


def test_settings_validate_runtime_server_options() -> None:
    assert Settings(_env_file=None, log_level="DEBUG").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="VERBOSE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_port=70000)


def test_environment_uses_the_documented_prefixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMECRAFTER_ENVIRONMENT", "test")

    assert Settings(_env_file=None).environment == "test"


def test_settings_reject_cloud_model_provider_in_zero_cost_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, model_provider="openai")
