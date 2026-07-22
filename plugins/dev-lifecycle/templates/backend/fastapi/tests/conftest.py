"""Hermetic test fixture: boots the real `create_app()` FastAPI app against
an in-memory, shared-cache sqlite database (aiosqlite + StaticPool — the
same pattern db-session/README.md's own test suite documents) instead of a
real DATABASE_URL/Postgres.

Uses a substitute lifespan (`_test_lifespan`) rather than the app's real
one: the real lifespan (app/main.py) reads `Settings().database_url` and
calls `configure_engine(url)` with no extra `engine_kwargs`, which would
open a *fresh, empty* anonymous in-memory sqlite database per connection —
StaticPool is what makes "in-memory" mean one shared database across the
whole test. Configuring the engine here (before the app/TestClient exist)
and creating/dropping tables inside `_test_lifespan` keeps that StaticPool
detail entirely inside the test suite; app/main.py's real lifespan is
never modified to know about it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.core.db import Base, configure_engine, get_engine
from app.core.db.session import _reset_engine_for_tests
from app.main import create_app

# Import side effect: registers every model on Base.metadata so
# Base.metadata.create_all()/drop_all() below actually create/drop each
# model's table. Goes through the app/models/__init__.py aggregator (Stage
# 3 #26, Step 3a) rather than importing `app.models.item` directly, so a
# future model added there is picked up here automatically.
import app.models  # noqa: F401,E402


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    configure_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    app = create_app(lifespan_ctx=_test_lifespan)
    with TestClient(app) as test_client:
        yield test_client
    _reset_engine_for_tests()
