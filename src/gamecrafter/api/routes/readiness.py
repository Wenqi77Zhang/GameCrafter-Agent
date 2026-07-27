"""Dependency readiness endpoint for local operations and containers."""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from gamecrafter.infrastructure.database.session import get_engine

router = APIRouter(tags=["system"])


class ReadinessResponse(BaseModel):
    """Safe readiness response without database credentials or error internals."""

    status: Literal["ready"]
    database: Literal["connected"]


@router.get("/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """Confirm the API can execute a database query."""

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from error
    return ReadinessResponse(status="ready", database="connected")
