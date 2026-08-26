from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecrafter.infrastructure.database.identity_service import (
    DatabaseIdentityService,
    IdentityError,
)
from gamecrafter.infrastructure.database.models import Base
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def _service():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return sessions, DatabaseIdentityService(sessions, session_hours=1)


def test_bootstrap_hashes_password_assigns_legacy_project_and_uses_revocable_session() -> None:
    sessions, identity = _service()
    project_id = DatabaseRunService(sessions).create_project(slug="legacy", name="Legacy")
    owner, token = identity.bootstrap(
        email="Owner@Example.com", display_name="Owner", password="a-secure-local-password"
    )
    assert identity.authenticate(token) == owner
    assert identity.project_role(project_id=project_id, user_id=UUID(str(owner["id"]))) == "owner"
    with sessions() as session:
        from gamecrafter.infrastructure.database.models import UserRecord

        user = session.get(UserRecord, UUID(str(owner["id"])))
        assert user is not None
        assert user.password_hash.startswith("scrypt$")
        assert "a-secure-local-password" not in user.password_hash
    identity.logout(token)
    assert identity.authenticate(token) is None


def test_team_invitation_is_email_bound_and_revocation_removes_project_access() -> None:
    _, identity = _service()
    owner, _ = identity.bootstrap(
        email="owner@example.com", display_name="Owner", password="owner-password-123"
    )
    # A second account is inserted through a separate empty database flow then copied is not safe;
    # create it directly with the same production password-hashing boundary for this service test.
    from gamecrafter.infrastructure.database.models import UserRecord

    with identity._sessions.begin() as session:  # noqa: SLF001 - isolated service fixture
        member = UserRecord(
            email_normalized="member@example.com",
            display_name="Member",
            password_hash=identity._hash_password("member-password-123"),  # noqa: SLF001
        )
        session.add(member)
        session.flush()
        member_id = member.id
    owner_id = UUID(str(owner["id"]))
    team = identity.create_team(user_id=owner_id, name="Studio")
    invitation, token = identity.invite(
        team_id=UUID(str(team["id"])),
        actor_id=owner_id,
        email="member@example.com",
        role="reviewer",
    )
    assert "token" not in invitation
    accepted = identity.accept_invitation(user_id=member_id, token=token)
    assert accepted["role"] == "reviewer"

    with identity._sessions.begin() as session:  # noqa: SLF001 - isolated service fixture
        from gamecrafter.infrastructure.database.models import ProjectRecord

        project = ProjectRecord(
            slug="team-game",
            name="Team game",
            owner_user_id=owner_id,
            team_id=UUID(str(team["id"])),
        )
        session.add(project)
        session.flush()
        project_id = project.id
    assert identity.project_role(project_id=project_id, user_id=member_id) == "reviewer"
    identity.revoke_member(
        team_id=UUID(str(team["id"])), actor_id=owner_id, member_user_id=member_id
    )
    assert identity.project_role(project_id=project_id, user_id=member_id) is None
    audit = identity.list_security_events(owner_id)
    assert {item["event_type"] for item in audit} >= {
        "team.created",
        "team.invitation_created",
        "team.member_revoked",
    }
    assert "member@example.com" not in str(audit)
    assert token not in str(audit)
    with pytest.raises(IdentityError, match="invalid or already used"):
        identity.accept_invitation(user_id=member_id, token=token)


def test_account_deletion_requires_exact_confirmation_and_removes_sessions() -> None:
    _, identity = _service()
    user, token = identity.bootstrap(
        email="departing@example.com",
        display_name="Departing",
        password="departing-password-123",
    )
    user_id = UUID(str(user["id"]))
    with pytest.raises(IdentityError, match="DELETE departing@example.com"):
        identity.delete_account(user_id=user_id, confirmation="DELETE")
    identity.delete_account(user_id=user_id, confirmation="DELETE departing@example.com")
    assert identity.authenticate(token) is None
