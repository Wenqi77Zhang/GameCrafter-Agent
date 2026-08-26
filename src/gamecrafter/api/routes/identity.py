"""Local account and small-team collaboration API."""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from gamecrafter.config.settings import get_settings
from gamecrafter.infrastructure.database.identity_service import (
    DatabaseIdentityService,
    IdentityError,
)
from gamecrafter.infrastructure.database.session import get_session_factory

router = APIRouter(prefix="/api/auth", tags=["identity-and-teams"])
SESSION_COOKIE = "gamecrafter_session"


@lru_cache
def identity_service() -> DatabaseIdentityService:
    return DatabaseIdentityService(
        get_session_factory(), session_hours=get_settings().auth_session_hours
    )


class AccountCommand(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(default="Local owner", min_length=1, max_length=120)


class InvitationRegistration(AccountCommand):
    invitation_token: str = Field(min_length=32, max_length=200)


class LoginCommand(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["editor", "reviewer", "viewer"]


class InviteAccept(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class AccountDelete(BaseModel):
    confirmation: str = Field(min_length=8, max_length=340)


def _fail(error: IdentityError) -> HTTPException:
    detail = str(error)
    code = 401 if "invalid email or password" in detail else 409
    if "permission denied" in detail:
        code = 403
    return HTTPException(status_code=code, detail=detail)


def _user_id(request: Request) -> UUID:
    value = getattr(request.state, "user", None)
    if not value:
        raise HTTPException(status_code=401, detail="authentication required")
    return UUID(str(value["id"]))


def request_actor_id(request: Request) -> str:
    """Use the authenticated user in audit lineage, or the explicit local single-user actor."""

    value = getattr(request.state, "user", None)
    return str(value["id"]) if value else "local-user"


def _require_enabled() -> None:
    if not get_settings().auth_enabled:
        raise HTTPException(status_code=409, detail="local accounts are disabled")


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        max_age=settings.auth_session_hours * 3600,
        path="/",
    )


@router.get("/status")
def auth_status(request: Request) -> dict[str, object]:
    settings = get_settings()
    return {
        "enabled": settings.auth_enabled,
        **(identity_service().status() if settings.auth_enabled else {"bootstrap_required": False}),
        "user": getattr(request.state, "user", None),
        "zero_cost": True,
    }


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
def bootstrap(command: AccountCommand, response: Response) -> dict[str, object]:
    _require_enabled()
    try:
        user, token = identity_service().bootstrap(
            email=command.email,
            display_name=command.display_name,
            password=command.password,
        )
    except IdentityError as error:
        raise _fail(error) from error
    _set_cookie(response, token)
    return user


@router.post("/login")
def login(command: LoginCommand, response: Response) -> dict[str, object]:
    _require_enabled()
    try:
        user, token = identity_service().login(email=command.email, password=command.password)
    except IdentityError as error:
        raise _fail(error) from error
    _set_cookie(response, token)
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(command: InvitationRegistration, response: Response) -> dict[str, object]:
    _require_enabled()
    try:
        user, token = identity_service().register_with_invitation(
            email=command.email,
            display_name=command.display_name,
            password=command.password,
            invitation_token=command.invitation_token,
        )
    except IdentityError as error:
        raise _fail(error) from error
    _set_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    gamecrafter_session: str | None = Cookie(default=None),
) -> None:
    identity_service().logout(gamecrafter_session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(request: Request) -> dict[str, object]:
    user_id = _user_id(request)
    return {"user": request.state.user, "teams": identity_service().list_teams(user_id)}


@router.get("/security-events")
def security_events(request: Request) -> dict[str, object]:
    return {"items": identity_service().list_security_events(_user_id(request))}


@router.delete("/me", status_code=204)
def delete_account(request: Request, response: Response, command: AccountDelete) -> None:
    try:
        identity_service().delete_account(
            user_id=_user_id(request), confirmation=command.confirmation
        )
    except IdentityError as error:
        raise _fail(error) from error
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/teams", status_code=201)
def create_team(request: Request, command: TeamCreate) -> dict[str, object]:
    return identity_service().create_team(user_id=_user_id(request), name=command.name)


@router.post("/teams/{team_id}/invitations", status_code=201)
def invite_member(request: Request, team_id: UUID, command: InviteCreate) -> dict[str, object]:
    try:
        invitation, token = identity_service().invite(
            team_id=team_id,
            actor_id=_user_id(request),
            email=command.email,
            role=command.role,
            maximum_members=get_settings().quota_team_members,
        )
    except IdentityError as error:
        raise _fail(error) from error
    return {**invitation, "acceptance_token": token}


@router.post("/invitations/accept")
def accept_invitation(request: Request, command: InviteAccept) -> dict[str, object]:
    try:
        return identity_service().accept_invitation(user_id=_user_id(request), token=command.token)
    except IdentityError as error:
        raise _fail(error) from error


@router.delete("/teams/{team_id}/members/{member_user_id}", status_code=204)
def revoke_member(request: Request, team_id: UUID, member_user_id: UUID) -> None:
    try:
        identity_service().revoke_member(
            team_id=team_id,
            actor_id=_user_id(request),
            member_user_id=member_user_id,
        )
    except IdentityError as error:
        raise _fail(error) from error
