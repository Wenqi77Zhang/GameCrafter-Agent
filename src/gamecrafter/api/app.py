"""FastAPI application factory."""

import re
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gamecrafter import __version__
from gamecrafter.api.routes.gdd import router as gdd_router
from gamecrafter.api.routes.health import router as health_router
from gamecrafter.api.routes.identity import SESSION_COOKIE, identity_service
from gamecrafter.api.routes.identity import router as identity_router
from gamecrafter.api.routes.knowledge import router as knowledge_router
from gamecrafter.api.routes.marketing import router as marketing_router
from gamecrafter.api.routes.readiness import router as readiness_router
from gamecrafter.api.routes.scripts import router as scripts_router
from gamecrafter.api.routes.workspace import router as workspace_router
from gamecrafter.config.settings import get_settings

_PROJECT_PATH = re.compile(r"^/api/projects/([0-9a-fA-F-]{36})(?:/|$)")
_RUN_PATH = re.compile(r"^/api/runs/([0-9a-fA-F-]{36})(?:/|$)")
_ROLE_RANK = {"viewer": 1, "reviewer": 2, "editor": 3, "owner": 4}


def _required_project_role(request: Request) -> str:
    path = request.url.path
    if request.method in {"GET", "HEAD"}:
        return "owner" if path.endswith("/portable-export") else "viewer"
    if request.method == "DELETE":
        return "owner"
    if any(marker in path for marker in ("/reviews", "/decision", "/revisions", "/closure")):
        return "reviewer"
    if path.endswith("/knowledge-snapshots"):
        return "reviewer"
    return "editor"


def create_app() -> FastAPI:
    """Create an API instance with validated local settings."""

    settings = get_settings()
    application = FastAPI(
        title="GameCrafter API",
        summary="Evidence-aware game knowledge and marketing workspace.",
        version=__version__,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.web_origin).rstrip("/")],
        allow_credentials=settings.auth_enabled,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def local_identity_boundary(request: Request, call_next):
        if not settings.auth_enabled:
            return await call_next(request)
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin.rstrip("/") != str(settings.web_origin).rstrip("/")
        ):
            return JSONResponse({"detail": "request origin denied"}, status_code=403)
        token = request.cookies.get(SESSION_COOKIE)
        user = identity_service().authenticate(token)
        request.state.user = user
        public = request.url.path in {
            "/health",
            "/readiness",
            "/api/health",
            "/api/readiness",
            "/api/auth/status",
            "/api/auth/bootstrap",
            "/api/auth/login",
            "/api/auth/register",
        }
        if not public and user is None:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        project_match = _PROJECT_PATH.match(request.url.path)
        run_match = _RUN_PATH.match(request.url.path)
        if (project_match or run_match) and user is not None:
            user_id = UUID(str(user["id"]))
            role = (
                identity_service().project_role(
                    project_id=UUID(project_match.group(1)), user_id=user_id
                )
                if project_match
                else identity_service().run_role(run_id=UUID(run_match.group(1)), user_id=user_id)
            )
            minimum = _required_project_role(request)
            if role is None or _ROLE_RANK[role] < _ROLE_RANK[minimum]:
                return JSONResponse({"detail": "project permission denied"}, status_code=403)
            request.state.project_role = role
        return await call_next(request)

    application.include_router(health_router)
    application.include_router(readiness_router)
    application.include_router(health_router, prefix="/api", include_in_schema=False)
    application.include_router(readiness_router, prefix="/api", include_in_schema=False)
    application.include_router(workspace_router)
    application.include_router(identity_router)
    application.include_router(gdd_router)
    application.include_router(knowledge_router)
    application.include_router(marketing_router)
    application.include_router(scripts_router)
    return application


app = create_app()
