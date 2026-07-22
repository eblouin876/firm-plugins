"""Liveness (`/health`) and readiness (`/readyz`) probes.

`/health` deliberately touches nothing but the process itself — no DB, no
dependency — so it answers even if the database is unreachable; that's
what makes it a *liveness* check (is the process up) rather than a
*readiness* check (is the process able to serve real traffic). `/readyz`
is the readiness counterpart: it runs a real `SELECT 1` through the
vendored `get_db` dependency, so a broken DB connection fails readiness
(and an orchestrator stops routing traffic to this instance) without
killing the process outright the way a liveness failure would."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.health import HealthStatus, ReadinessStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="Health Check")
async def health_check() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/readyz", response_model=ReadinessStatus, summary="Readiness Check")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> ReadinessStatus:
    await db.execute(text("SELECT 1"))
    return ReadinessStatus(status="ready")
