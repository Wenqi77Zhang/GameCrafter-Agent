"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gamecrafter import __version__
from gamecrafter.api.routes.health import router as health_router
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
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    return application


app = create_app()
