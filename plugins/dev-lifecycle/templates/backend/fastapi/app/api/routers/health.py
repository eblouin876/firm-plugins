"""Liveness (`/health`) and readiness (`/readyz`) probes.

`/health` deliberately touches nothing but the process itself — no DB, no
dependency — so it answers even if the database is unreachable; that's
what makes it a *liveness* check (is the process up) rather than a
*readiness* check (is the process able to serve real traffic). `/readyz`
is the readiness counterpart: it runs a real `SELECT 1` through the
vendored `get_db` dependency, so a broken DB connection fails readiness
(and an orchestrator stops routing traffic to this instance) without
killing the process outright the way a liveness failure would.

JUDGMENT CALL (Stage 3 #26, Step 3a): a DB-down `/readyz` returns HTTP 503
with a plain `ReadinessStatus(status="unavailable")` body, NOT the
`ErrorEnvelope` the rest of this app's errors use. `ErrorCode`
(app/core/errors.py) is a closed, versioned enum with no
`service_unavailable` member — adding one for a readiness probe (which
orchestrators poll and parse by status code, not by envelope shape) is the
same kind of contract change `app/api/routers/auth.py`'s stub 501s
decline to make unilaterally. `OperationalError`/`DBAPIError` (from
`sqlalchemy.exc`) are caught specifically — a real DB-connectivity failure
— rather than a bare `except Exception`, so a genuine application bug
inside the probe still surfaces as an unhandled 500 via `app/main.py`'s
catch-all, instead of being misreported as "DB down"."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.db import get_db
from app.schemas.health import HealthStatus, ReadinessStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="Health Check")
async def health_check() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/readyz",
    response_model=ReadinessStatus,
    summary="Readiness Check",
    responses={503: {"model": ReadinessStatus, "description": "Database unreachable."}},
)
async def readiness_check(db: AsyncSession = Depends(get_db)) -> ReadinessStatus | JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except (OperationalError, DBAPIError):
        # Roll back explicitly here (mirroring get_db()'s own except branch)
        # rather than letting the exception propagate into get_db()'s
        # generator boundary — this route deliberately swallows the error to
        # render a 503 instead of the 500 an unhandled exception would
        # become, so get_db()'s post-route commit must see a clean session,
        # not one left mid-failed-transaction.
        await db.rollback()
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ReadinessStatus(status="unavailable").model_dump(mode="json"),
        )
    return ReadinessStatus(status="ready")
