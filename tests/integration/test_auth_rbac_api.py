from fastapi.testclient import TestClient

from gamecrafter.api.app import create_app
from gamecrafter.api.routes import identity, workspace
from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.models import Base
from gamecrafter.infrastructure.database.session import (
    get_engine,
    get_session_factory,
)


def _clear_runtime_caches() -> None:
    identity.identity_service.cache_clear()
    workspace._service.cache_clear()  # noqa: SLF001 - API isolation fixture
    workspace._local_source_service.cache_clear()  # noqa: SLF001
    workspace._portability_service.cache_clear()  # noqa: SLF001
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()


def test_disabled_identity_cannot_be_used_as_a_hidden_login_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "GAMECRAFTER_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'disabled.sqlite3').as_posix()}",
    )
    monkeypatch.setenv("GAMECRAFTER_AUTH_ENABLED", "false")
    _clear_runtime_caches()
    client = TestClient(create_app())
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "irrelevant"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "local accounts are disabled"
    finally:
        client.close()
        get_engine().dispose()
        _clear_runtime_caches()


def test_invited_reviewer_can_read_then_immediately_loses_access_after_revocation(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("GAMECRAFTER_DATABASE_URL", f"sqlite+pysqlite:///{database.as_posix()}")
    monkeypatch.setenv("GAMECRAFTER_OBJECT_STORAGE_PATH", str(tmp_path / "objects"))
    monkeypatch.setenv("GAMECRAFTER_AUTH_ENABLED", "true")
    monkeypatch.setenv("GAMECRAFTER_WEB_ORIGIN", "http://localhost:5173")
    _clear_runtime_caches()
    Base.metadata.create_all(get_engine())
    app = create_app()
    owner = TestClient(app)
    member = TestClient(app)
    anonymous = TestClient(app)
    try:
        assert owner.get("/api/auth/status").json()["bootstrap_required"] is True
        assert (
            owner.post(
                "/api/auth/bootstrap",
                json={
                    "email": "owner@example.com",
                    "display_name": "Owner",
                    "password": "owner-password-123",
                },
            ).status_code
            == 201
        )
        project = owner.post(
            "/api/projects",
            json={"slug": "isolated", "name": "Isolated", "default_locale": "zh-CN"},
        ).json()
        run = owner.post(
            f"/api/projects/{project['id']}/source-discoveries",
            headers={"Idempotency-Key": "owner-discovery-1"},
            json={
                "listing_urls": ["https://nte.perfectworld.com/en/article/news/index.html"],
                "candidate_limit": 5,
            },
        ).json()
        team = owner.get("/api/auth/me").json()["teams"][0]
        invitation = owner.post(
            f"/api/auth/teams/{team['id']}/invitations",
            json={"email": "reviewer@example.com", "role": "reviewer"},
        ).json()
        assert (
            member.post(
                "/api/auth/register",
                json={
                    "email": "reviewer@example.com",
                    "display_name": "Reviewer",
                    "password": "reviewer-password-123",
                    "invitation_token": invitation["acceptance_token"],
                },
            ).status_code
            == 201
        )
        assert member.get(f"/api/projects/{project['id']}/sources").status_code == 200
        assert member.get(f"/api/runs/{run['id']}").status_code == 200
        assert (
            member.post(
                f"/api/runs/{run['id']}/retry",
                headers={"Idempotency-Key": "reviewer-retry-denied-1"},
            ).status_code
            == 403
        )
        assert member.get(f"/api/projects/{project['id']}/portable-export").status_code == 403
        assert (
            member.post(
                f"/api/projects/{project['id']}/local-sources",
                headers={"Idempotency-Key": "reviewer-cannot-edit-1"},
                json={
                    "document_key": "blocked",
                    "kind": "document",
                    "title": "Blocked",
                    "filename": "blocked.txt",
                    "content": "This write must be denied.",
                    "media_type": "text/plain",
                    "locale": "en",
                    "region": "private",
                },
            ).status_code
            == 403
        )
        assert anonymous.get(f"/api/projects/{project['id']}/sources").status_code == 401
        assert (
            owner.delete(
                f"/api/auth/teams/{team['id']}/members/{member.get('/api/auth/me').json()['user']['id']}"
            ).status_code
            == 204
        )
        assert member.get(f"/api/projects/{project['id']}/sources").status_code == 403
        assert member.get(f"/api/runs/{run['id']}").status_code == 403
    finally:
        owner.close()
        member.close()
        anonymous.close()
        get_engine().dispose()
        _clear_runtime_caches()
