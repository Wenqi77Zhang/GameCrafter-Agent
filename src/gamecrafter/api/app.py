"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gamecrafter import __version__
from gamecrafter.api.routes.health import router as health_router
from gamecrafter.api.routes.knowledge import router as knowledge_router
from gamecrafter.api.routes.readiness import router as readiness_router
from gamecrafter.api.routes.workspace import router as workspace_router
from gamecrafter.config.settings import get_settings


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
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(readiness_router)
    application.include_router(health_router, prefix="/api", include_in_schema=False)
    application.include_router(readiness_router, prefix="/api", include_in_schema=False)
    application.include_router(workspace_router)
    application.include_router(knowledge_router)
    return application


app = create_app()
