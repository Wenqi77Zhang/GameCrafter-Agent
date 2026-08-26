"""Local-first identity, opaque sessions, tenant membership, and RBAC."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    AuditEventRecord,
    AuthLoginThrottleRecord,
    ProjectRecord,
    SecurityAuditRecord,
    TeamInvitationRecord,
    TeamMembershipRecord,
    TeamRecord,
    UserRecord,
    UserSessionRecord,
    WorkflowRunRecord,
    utc_now,
)

Role = Literal["owner", "editor", "reviewer", "viewer"]
_ROLE_RANK: dict[str, int] = {"viewer": 1, "reviewer": 2, "editor": 3, "owner": 4}
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class IdentityError(RuntimeError):
    """Safe authentication, invitation, quota, or authorization error."""


class DatabaseIdentityService:
    def __init__(self, session_factory: sessionmaker[Session], *, session_hours: int = 168) -> None:
        self._sessions = session_factory
        self._session_hours = session_hours
        self._dummy_password_hash = self._hash_password(secrets.token_urlsafe(24))

    def status(self) -> dict[str, object]:
        with self._sessions() as session:
            return {
                "bootstrap_required": int(session.scalar(select(func.count(UserRecord.id))) or 0)
                == 0
            }

    def bootstrap(
        self, *, email: str, display_name: str, password: str
    ) -> tuple[dict[str, object], str]:
        clean_email = self._email(email)
        clean_name = self._clean(display_name, "display name", 120)
        password_hash = self._hash_password(password)
        with self._sessions.begin() as session:
            if int(session.scalar(select(func.count(UserRecord.id))) or 0):
                raise IdentityError("local owner account already exists")
            user = UserRecord(
                email_normalized=clean_email,
                display_name=clean_name,
                password_hash=password_hash,
            )
            session.add(user)
            session.flush()
            team = TeamRecord(
                slug=f"personal-{str(user.id)[:8]}",
                name=f"{clean_name}'s workspace",
                created_by=user.id,
            )
            session.add(team)
            session.flush()
            session.add(TeamMembershipRecord(team_id=team.id, user_id=user.id, role="owner"))
            self._audit(session, "account.owner_bootstrapped", user.id, team.id)
            for project in session.scalars(
                select(ProjectRecord).where(ProjectRecord.owner_user_id.is_(None))
            ):
                project.owner_user_id = user.id
                project.team_id = team.id
            token = self._new_session(session, user.id)
            self._audit(session, "account.login_succeeded", user.id, None)
        return self._user(user), token

    def login(self, *, email: str, password: str) -> tuple[dict[str, object], str]:
        clean_email = self._email(email)
        if self._login_blocked(clean_email):
            raise IdentityError("invalid email or password")
        with self._sessions.begin() as session:
            user = session.scalar(
                select(UserRecord).where(UserRecord.email_normalized == clean_email)
            )
            valid_password = self._verify_password(
                password, user.password_hash if user is not None else self._dummy_password_hash
            )
            if user is None or user.status != "active" or not valid_password:
                invalid = True
            else:
                invalid = False
                digest = hashlib.sha256(clean_email.encode()).hexdigest()
                session.execute(
                    delete(AuthLoginThrottleRecord).where(
                        AuthLoginThrottleRecord.email_sha256 == digest
                    )
                )
                token = self._new_session(session, user.id)
                self._audit(session, "account.login_succeeded", user.id, None)
                result = self._user(user)
        if invalid:
            self._record_login_failure(clean_email)
            raise IdentityError("invalid email or password")
        return result, token

    def _login_blocked(self, clean_email: str) -> bool:
        digest = hashlib.sha256(clean_email.encode()).hexdigest()
        now = utc_now()
        with self._sessions() as session:
            record = session.get(AuthLoginThrottleRecord, digest)
            if record is None or record.blocked_until is None:
                return False
            blocked_until = record.blocked_until
            if blocked_until.tzinfo is None:
                blocked_until = blocked_until.replace(tzinfo=UTC)
            return blocked_until > now

    def _record_login_failure(self, clean_email: str) -> None:
        digest = hashlib.sha256(clean_email.encode()).hexdigest()
        now = utc_now()
        window = timedelta(minutes=15)
        with self._sessions.begin() as session:
            record = session.get(AuthLoginThrottleRecord, digest)
            if record is None:
                record = AuthLoginThrottleRecord(
                    email_sha256=digest, failure_count=1, window_started_at=now
                )
                session.add(record)
                return
            started = record.window_started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if started + window <= now:
                record.failure_count = 1
                record.window_started_at = now
                record.blocked_until = None
            else:
                record.failure_count += 1
                if record.failure_count >= 5:
                    record.blocked_until = now + window
            record.updated_at = now

    def register_with_invitation(
        self,
        *,
        email: str,
        display_name: str,
        password: str,
        invitation_token: str,
    ) -> tuple[dict[str, object], str]:
        clean_email = self._email(email)
        clean_name = self._clean(display_name, "display name", 120)
        password_hash = self._hash_password(password)
        digest = hashlib.sha256(invitation_token.encode()).hexdigest()
        now = utc_now()
        with self._sessions.begin() as session:
            if (
                session.scalar(
                    select(UserRecord.id).where(UserRecord.email_normalized == clean_email)
                )
                is not None
            ):
                raise IdentityError("account already exists; sign in and accept the invitation")
            invitation = session.scalar(
                select(TeamInvitationRecord)
                .where(TeamInvitationRecord.token_sha256 == digest)
                .with_for_update()
            )
            if invitation is None or invitation.status != "pending":
                raise IdentityError("invitation is invalid or already used")
            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                invitation.status = "expired"
                invitation.decided_at = now
                raise IdentityError("invitation has expired")
            if invitation.email_normalized != clean_email:
                raise IdentityError("invitation email does not match the new account")
            user = UserRecord(
                email_normalized=clean_email,
                display_name=clean_name,
                password_hash=password_hash,
            )
            session.add(user)
            session.flush()
            session.add(
                TeamMembershipRecord(
                    team_id=invitation.team_id,
                    user_id=user.id,
                    role=invitation.role,
                )
            )
            invitation.status = "accepted"
            invitation.accepted_by = user.id
            invitation.decided_at = now
            self._audit(
                session,
                "team.invitation_registered",
                user.id,
                invitation.team_id,
                {"role": invitation.role},
            )
            token = self._new_session(session, user.id)
            result = self._user(user)
        return result, token

    def authenticate(self, token: str | None) -> dict[str, object] | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(UTC)
        with self._sessions() as session:
            record = session.scalar(
                select(UserSessionRecord)
                .join(UserRecord, UserRecord.id == UserSessionRecord.user_id)
                .where(
                    UserSessionRecord.token_sha256 == digest,
                    UserSessionRecord.revoked_at.is_(None),
                    UserSessionRecord.expires_at > now,
                    UserRecord.status == "active",
                )
            )
            if record is None:
                return None
            user = session.get(UserRecord, record.user_id)
            return self._user(user)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._sessions.begin() as session:
            record = session.scalar(
                select(UserSessionRecord).where(UserSessionRecord.token_sha256 == digest)
            )
            if record is not None and record.revoked_at is None:
                record.revoked_at = utc_now()

    def list_teams(self, user_id: UUID) -> list[dict[str, object]]:
        with self._sessions() as session:
            memberships = list(
                session.scalars(
                    select(TeamMembershipRecord)
                    .where(
                        TeamMembershipRecord.user_id == user_id,
                        TeamMembershipRecord.status == "active",
                    )
                    .order_by(TeamMembershipRecord.created_at)
                )
            )
            result = []
            for membership in memberships:
                team = session.get(TeamRecord, membership.team_id)
                if team is not None:
                    result.append(self._team(session, team, membership.role))
            return result

    def list_security_events(self, user_id: UUID, limit: int = 100) -> list[dict[str, object]]:
        with self._sessions() as session:
            team_ids = select(TeamMembershipRecord.team_id).where(
                TeamMembershipRecord.user_id == user_id,
                TeamMembershipRecord.status == "active",
            )
            records = session.scalars(
                select(SecurityAuditRecord)
                .where(
                    (SecurityAuditRecord.actor_user_id == user_id)
                    | (SecurityAuditRecord.team_id.in_(team_ids))
                )
                .order_by(SecurityAuditRecord.created_at.desc())
                .limit(limit)
            )
            return [
                {
                    "id": str(item.id),
                    "event_type": item.event_type,
                    "actor_user_id": str(item.actor_user_id) if item.actor_user_id else None,
                    "team_id": str(item.team_id) if item.team_id else None,
                    "payload": item.payload,
                    "created_at": item.created_at.isoformat(),
                }
                for item in records
            ]

    def create_team(self, *, user_id: UUID, name: str) -> dict[str, object]:
        clean_name = self._clean(name, "team name", 160)
        with self._sessions.begin() as session:
            suffix = secrets.token_hex(4)
            team = TeamRecord(slug=f"team-{suffix}", name=clean_name, created_by=user_id)
            session.add(team)
            session.flush()
            session.add(TeamMembershipRecord(team_id=team.id, user_id=user_id, role="owner"))
            self._audit(session, "team.created", user_id, team.id)
            result = self._team(session, team, "owner")
        return result

    def invite(
        self,
        *,
        team_id: UUID,
        actor_id: UUID,
        email: str,
        role: Literal["editor", "reviewer", "viewer"],
        expiry_hours: int = 72,
        maximum_members: int = 20,
    ) -> tuple[dict[str, object], str]:
        clean_email = self._email(email)
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self._sessions.begin() as session:
            self._require_role(session, team_id, actor_id, "owner")
            member_count = int(
                session.scalar(
                    select(func.count(TeamMembershipRecord.id)).where(
                        TeamMembershipRecord.team_id == team_id,
                        TeamMembershipRecord.status == "active",
                    )
                )
                or 0
            )
            if member_count >= maximum_members:
                raise IdentityError(f"local team member quota reached ({maximum_members})")
            record = TeamInvitationRecord(
                team_id=team_id,
                email_normalized=clean_email,
                role=role,
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                status="pending",
                expires_at=now + timedelta(hours=expiry_hours),
                created_by=actor_id,
            )
            session.add(record)
            session.flush()
            self._audit(
                session,
                "team.invitation_created",
                actor_id,
                team_id,
                {"role": role, "email_sha256": hashlib.sha256(clean_email.encode()).hexdigest()},
            )
            result = self._invitation(record)
        return result, token

    def accept_invitation(self, *, user_id: UUID, token: str) -> dict[str, object]:
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = utc_now()
        with self._sessions.begin() as session:
            user = session.get(UserRecord, user_id)
            invitation = session.scalar(
                select(TeamInvitationRecord)
                .where(TeamInvitationRecord.token_sha256 == digest)
                .with_for_update()
            )
            if user is None or invitation is None or invitation.status != "pending":
                raise IdentityError("invitation is invalid or already used")
            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                invitation.status = "expired"
                invitation.decided_at = now
                raise IdentityError("invitation has expired")
            if invitation.email_normalized != user.email_normalized:
                raise IdentityError("invitation email does not match the signed-in account")
            membership = session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == invitation.team_id,
                    TeamMembershipRecord.user_id == user_id,
                )
            )
            if membership is None:
                membership = TeamMembershipRecord(
                    team_id=invitation.team_id, user_id=user_id, role=invitation.role
                )
                session.add(membership)
            else:
                membership.role = invitation.role
                membership.status = "active"
                membership.revoked_at = None
            invitation.status = "accepted"
            invitation.accepted_by = user_id
            invitation.decided_at = now
            self._audit(
                session,
                "team.invitation_accepted",
                user_id,
                invitation.team_id,
                {"role": invitation.role},
            )
            team = session.get(TeamRecord, invitation.team_id)
            result = self._team(session, team, membership.role)
        return result

    def revoke_member(self, *, team_id: UUID, actor_id: UUID, member_user_id: UUID) -> None:
        if actor_id == member_user_id:
            raise IdentityError("owner cannot revoke their own membership")
        with self._sessions.begin() as session:
            self._require_role(session, team_id, actor_id, "owner")
            membership = session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == team_id,
                    TeamMembershipRecord.user_id == member_user_id,
                    TeamMembershipRecord.status == "active",
                )
            )
            if membership is None:
                raise IdentityError("active team member not found")
            if membership.role == "owner":
                raise IdentityError("another owner cannot be revoked")
            membership.status = "revoked"
            membership.revoked_at = utc_now()
            self._audit(
                session,
                "team.member_revoked",
                actor_id,
                team_id,
                {"member_user_id": str(member_user_id), "prior_role": membership.role},
            )

    def change_member_role(
        self,
        *,
        team_id: UUID,
        actor_id: UUID,
        member_user_id: UUID,
        role: Literal["editor", "reviewer", "viewer"],
    ) -> dict[str, object]:
        """Change a non-owner role immediately and preserve the prior role in the audit trail."""

        with self._sessions.begin() as session:
            self._require_role(session, team_id, actor_id, "owner")
            membership = session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == team_id,
                    TeamMembershipRecord.user_id == member_user_id,
                    TeamMembershipRecord.status == "active",
                )
            )
            if membership is None:
                raise IdentityError("active team member not found")
            if membership.role == "owner":
                raise IdentityError("transfer ownership before changing the owner role")
            prior_role = membership.role
            membership.role = role
            self._audit(
                session,
                "team.member_role_changed",
                actor_id,
                team_id,
                {
                    "member_user_id": str(member_user_id),
                    "prior_role": prior_role,
                    "new_role": role,
                },
            )
            user = session.get(UserRecord, member_user_id)
            return {
                "user_id": str(member_user_id),
                "display_name": user.display_name,
                "email": user.email_normalized,
                "role": role,
            }

    def transfer_ownership(
        self, *, team_id: UUID, actor_id: UUID, target_user_id: UUID
    ) -> dict[str, object]:
        """Atomically transfer a team and every team project to an active member."""

        if actor_id == target_user_id:
            raise IdentityError("target user is already the owner")
        with self._sessions.begin() as session:
            owner = self._require_role(session, team_id, actor_id, "owner")
            target = session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == team_id,
                    TeamMembershipRecord.user_id == target_user_id,
                    TeamMembershipRecord.status == "active",
                )
            )
            if target is None:
                raise IdentityError("active target team member not found")
            if target.role == "owner":
                raise IdentityError("target user is already the owner")
            prior_target_role = target.role
            owner.role = "editor"
            target.role = "owner"
            team = session.get(TeamRecord, team_id)
            if team is None:
                raise IdentityError("team not found")
            team.created_by = target_user_id
            session.execute(
                update(ProjectRecord)
                .where(ProjectRecord.team_id == team_id)
                .values(owner_user_id=target_user_id)
            )
            self._audit(
                session,
                "team.ownership_transferred",
                actor_id,
                team_id,
                {
                    "prior_owner_user_id": str(actor_id),
                    "new_owner_user_id": str(target_user_id),
                    "prior_target_role": prior_target_role,
                },
            )
            return self._team(session, team, "editor")

    def delete_account(self, *, user_id: UUID, confirmation: str) -> None:
        with self._sessions.begin() as session:
            user = session.get(UserRecord, user_id)
            if user is None:
                raise IdentityError("account not found")
            if confirmation != f"DELETE {user.email_normalized}":
                raise IdentityError(
                    f'type "DELETE {user.email_normalized}" to confirm account deletion'
                )
            projects = int(
                session.scalar(
                    select(func.count(ProjectRecord.id)).where(
                        ProjectRecord.owner_user_id == user_id
                    )
                )
                or 0
            )
            if projects:
                raise IdentityError("delete or transfer every owned project first")
            owned = list(
                session.scalars(
                    select(TeamMembershipRecord).where(
                        TeamMembershipRecord.user_id == user_id,
                        TeamMembershipRecord.role == "owner",
                        TeamMembershipRecord.status == "active",
                    )
                )
            )
            for membership in owned:
                other_members = int(
                    session.scalar(
                        select(func.count(TeamMembershipRecord.id)).where(
                            TeamMembershipRecord.team_id == membership.team_id,
                            TeamMembershipRecord.user_id != user_id,
                            TeamMembershipRecord.status == "active",
                        )
                    )
                    or 0
                )
                if other_members:
                    raise IdentityError("transfer team ownership before deleting the account")
                team_projects = int(
                    session.scalar(
                        select(func.count(ProjectRecord.id)).where(
                            ProjectRecord.team_id == membership.team_id
                        )
                    )
                    or 0
                )
                if team_projects:
                    raise IdentityError("delete or transfer every team project first")
                session.execute(
                    delete(TeamInvitationRecord).where(
                        TeamInvitationRecord.team_id == membership.team_id
                    )
                )
                session.execute(
                    delete(TeamMembershipRecord).where(
                        TeamMembershipRecord.team_id == membership.team_id
                    )
                )
                session.execute(delete(TeamRecord).where(TeamRecord.id == membership.team_id))
            session.execute(
                delete(TeamInvitationRecord).where(
                    (TeamInvitationRecord.created_by == user_id)
                    | (TeamInvitationRecord.accepted_by == user_id)
                )
            )
            session.execute(
                delete(TeamMembershipRecord).where(TeamMembershipRecord.user_id == user_id)
            )
            session.execute(delete(UserSessionRecord).where(UserSessionRecord.user_id == user_id))
            self._audit(session, "account.deleted", user_id, None)
            session.delete(user)

    def project_role(self, *, project_id: UUID, user_id: UUID) -> str | None:
        with self._sessions() as session:
            project = session.get(ProjectRecord, project_id)
            if project is None:
                return None
            if project.owner_user_id == user_id:
                return "owner"
            if project.team_id is None:
                return None
            membership = session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == project.team_id,
                    TeamMembershipRecord.user_id == user_id,
                    TeamMembershipRecord.status == "active",
                )
            )
            return membership.role if membership else None

    def run_role(self, *, run_id: UUID, user_id: UUID) -> str | None:
        """Resolve a run through its project so legacy run URLs cannot bypass tenant RBAC."""

        with self._sessions() as session:
            project_id = session.scalar(
                select(WorkflowRunRecord.project_id).where(WorkflowRunRecord.id == run_id)
            )
        return self.project_role(project_id=project_id, user_id=user_id) if project_id else None

    def accessible_project_ids(self, user_id: UUID) -> set[str]:
        with self._sessions() as session:
            team_ids = select(TeamMembershipRecord.team_id).where(
                TeamMembershipRecord.user_id == user_id,
                TeamMembershipRecord.status == "active",
            )
            values = session.scalars(
                select(ProjectRecord.id).where(
                    (ProjectRecord.owner_user_id == user_id) | (ProjectRecord.team_id.in_(team_ids))
                )
            )
            return {str(item) for item in values}

    def default_team_id(self, user_id: UUID) -> UUID:
        with self._sessions() as session:
            membership = session.scalar(
                select(TeamMembershipRecord)
                .where(
                    TeamMembershipRecord.user_id == user_id,
                    TeamMembershipRecord.status == "active",
                )
                .order_by(TeamMembershipRecord.created_at)
                .limit(1)
            )
            if membership is None:
                raise IdentityError("user has no active workspace")
            return membership.team_id

    def enforce_project_quota(self, user_id: UUID, maximum: int) -> None:
        with self._sessions() as session:
            count = int(
                session.scalar(
                    select(func.count(ProjectRecord.id)).where(
                        ProjectRecord.owner_user_id == user_id
                    )
                )
                or 0
            )
            if count >= maximum:
                raise IdentityError(f"local project quota reached ({maximum})")

    def assign_project(self, *, project_id: UUID, user_id: UUID, team_id: UUID) -> None:
        with self._sessions.begin() as session:
            self._require_role(session, team_id, user_id, "editor")
            project = session.get(ProjectRecord, project_id)
            if project is None:
                raise IdentityError("project not found")
            project.owner_user_id = user_id
            project.team_id = team_id
            session.add(
                AuditEventRecord(
                    project_id=project.id,
                    event_type="project.tenant_assigned",
                    actor_type="human",
                    actor_id=str(user_id),
                    payload={"team_id": str(team_id)},
                )
            )

    def _require_role(
        self, session: Session, team_id: UUID, user_id: UUID, minimum: Role
    ) -> TeamMembershipRecord:
        membership = session.scalar(
            select(TeamMembershipRecord).where(
                TeamMembershipRecord.team_id == team_id,
                TeamMembershipRecord.user_id == user_id,
                TeamMembershipRecord.status == "active",
            )
        )
        if membership is None or _ROLE_RANK[membership.role] < _ROLE_RANK[minimum]:
            raise IdentityError("team permission denied")
        return membership

    def _new_session(self, session: Session, user_id: UUID) -> str:
        token = secrets.token_urlsafe(48)
        session.add(
            UserSessionRecord(
                user_id=user_id,
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=utc_now() + timedelta(hours=self._session_hours),
            )
        )
        return token

    @staticmethod
    def _audit(
        session: Session,
        event_type: str,
        actor_user_id: UUID | None,
        team_id: UUID | None,
        payload: dict[str, object] | None = None,
    ) -> None:
        session.add(
            SecurityAuditRecord(
                event_type=event_type,
                actor_user_id=actor_user_id,
                team_id=team_id,
                payload=payload or {},
            )
        )

    @staticmethod
    def _hash_password(password: str) -> str:
        if len(password) < 12 or len(password) > 200:
            raise IdentityError("password must contain 12 to 200 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt, expected = encoded.split("$")
            if algorithm != "scrypt":
                return False
            actual = hashlib.scrypt(
                password.encode(),
                salt=bytes.fromhex(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=32,
            )
            return hmac.compare_digest(actual, bytes.fromhex(expected))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _email(value: str) -> str:
        clean = value.strip().casefold()
        if len(clean) > 320 or _EMAIL.fullmatch(clean) is None:
            raise IdentityError("valid email is required")
        return clean

    @staticmethod
    def _clean(value: str, label: str, maximum: int) -> str:
        clean = " ".join(value.split())
        if not clean or len(clean) > maximum:
            raise IdentityError(f"{label} must contain 1 to {maximum} characters")
        return clean

    @staticmethod
    def _user(user: UserRecord) -> dict[str, object]:
        return {
            "id": str(user.id),
            "email": user.email_normalized,
            "display_name": user.display_name,
            "status": user.status,
        }

    @staticmethod
    def _team(session: Session, team: TeamRecord, role: str) -> dict[str, object]:
        members = list(
            session.execute(
                select(TeamMembershipRecord, UserRecord)
                .join(UserRecord, UserRecord.id == TeamMembershipRecord.user_id)
                .where(
                    TeamMembershipRecord.team_id == team.id,
                    TeamMembershipRecord.status == "active",
                )
            )
        )
        return {
            "id": str(team.id),
            "slug": team.slug,
            "name": team.name,
            "role": role,
            "members": [
                {
                    "user_id": str(membership.user_id),
                    "display_name": user.display_name,
                    "email": user.email_normalized,
                    "role": membership.role,
                }
                for membership, user in members
            ],
        }

    @staticmethod
    def _invitation(item: TeamInvitationRecord) -> dict[str, object]:
        return {
            "id": str(item.id),
            "team_id": str(item.team_id),
            "email": item.email_normalized,
            "role": item.role,
            "status": item.status,
            "expires_at": item.expires_at.isoformat(),
        }
