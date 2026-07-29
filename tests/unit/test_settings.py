from gamecrafter.config.settings import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.api_host == "127.0.0.1"
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert "gamecrafter_local" not in str(settings.database_url)
    assert settings.object_storage_backend == "filesystem"
    assert settings.object_storage_path.as_posix() == "data/objects"
    assert settings.source_max_concurrency_per_host == 1
    assert settings.source_global_max_concurrency == 3
    assert settings.source_quick_candidate_limit == 30
    assert settings.source_targeted_candidate_limit == 100
    assert settings.worker_id == "local-worker"
    assert settings.model_provider == "disabled"
    assert settings.model_api_key is None
