# Vendored from templates/components/backend/db-session; keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.

"""Framework-neutral-within-SQLAlchemy async session management: an async
engine factory from a DATABASE_URL, an async_sessionmaker, and a `get_db`
FastAPI-shaped dependency with commit/rollback/close discipline. SQLAlchemy
2.0 async (`AsyncEngine`/`AsyncSession`), pinned per
references/compatibility-matrix.md's Backend — Python row. Canon:
references/backend/sqlalchemy.md ("Sessions & transactions" — one session
per request via a dependency with guaranteed cleanup, explicit commit/
rollback boundaries, never block the event loop with sync DB calls).

Drop-in: copy this file into app/core/db/session.py, alongside mixins.py
and repository.py (also SQLAlchemy-specific). Call `configure_engine
(DATABASE_URL)` once at app startup (FastAPI lifespan/on_startup); every
route then depends on `get_db` directly (`Depends(get_db)`) with no
per-route wiring:

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/widgets")
    async def list_widgets(db: AsyncSession = Depends(get_db)):
        ...

SQLAlchemy-specific — Django's ORM has its own connection/transaction
model (autocommit-per-request or explicit `transaction.atomic()`) with no
`AsyncSession`/`async_sessionmaker` equivalent; Stage 4's Django track does
not reuse this file.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Bare (sync-driver) scheme -> the async driver this module actually needs.
# Covers the schemes this catalog's own dialects use (sqlite for hermetic
# tests, postgresql for prod); a scheme not listed here (an already-async
# scheme like `postgresql+asyncpg`, or a dialect this catalog doesn't
# target) is left to create_async_engine's own error, not guarded here.
_ASYNC_DRIVER_HINT: dict[str, str] = {
    "postgresql": "postgresql+asyncpg://",
    "postgres": "postgresql+asyncpg://",
    "sqlite": "sqlite+aiosqlite://",
    "mysql": "mysql+aiomysql://",
}


def _require_async_driver(database_url: str) -> None:
    """Fails fast, with an actionable message, when `database_url` uses a
    bare synchronous-driver scheme (`postgresql://`, `sqlite://`, ...)
    instead of an async one (`postgresql+asyncpg://`,
    `sqlite+aiosqlite://`, ...). Without this check, `create_async_engine`
    still accepts a sync scheme, then fails later — either at the first
    query, or with an import error for a sync driver package this project
    never installed — surfacing a confusing, deep stack trace far from the
    actual mistake (a config value, not this module). Only checks schemes
    this catalog's own dialects use; an already-async scheme (`+asyncpg`,
    `+aiosqlite`, ...) always passes through untouched."""
    scheme = database_url.split("://", 1)[0] if "://" in database_url else database_url
    if "+" in scheme:
        return  # already names a driver, e.g. postgresql+asyncpg -- not our concern
    hint = _ASYNC_DRIVER_HINT.get(scheme.lower())
    if hint is None:
        return  # not one of the schemes we have an opinion about
    raise ValueError(
        f"DATABASE_URL {database_url!r} uses the synchronous '{scheme}://' scheme, "
        f"but configure_engine() requires an async driver — use {hint!r} instead "
        f"(e.g. '{hint}user:pass@host/dbname'). Install the matching async driver "
        "package if it isn't already a dependency."
    )


def configure_engine(database_url: str, *, echo: bool = False, **engine_kwargs: Any) -> AsyncEngine:
    """Builds (and caches, module-level) the async engine and its
    sessionmaker from a DATABASE_URL. Call exactly once at app startup —
    e.g. a FastAPI lifespan handler reading `settings.DATABASE_URL` (see
    settings/). Validates `database_url` names an async driver scheme
    first (see `_require_async_driver`) — fails fast with an actionable
    message instead of a deep `create_async_engine` stack trace.
    `pool_pre_ping=True` is the default unless overridden via
    `engine_kwargs` — it recycles a connection dropped by the DB server
    (idle timeout, failover) instead of surfacing a stale-connection error
    to a request. `**engine_kwargs` passes through to
    `create_async_engine` untouched — a test suite uses it to inject
    `poolclass=StaticPool` for a shared in-memory sqlite engine (see
    tests/test_session.py); a prod deployment might use it to tune
    `pool_size`/`max_overflow`."""
    _require_async_driver(database_url)
    global _engine, _sessionmaker
    engine_kwargs.setdefault("pool_pre_ping", True)
    _engine = create_async_engine(database_url, echo=echo, **engine_kwargs)
    _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Returns the engine configured by `configure_engine()`. Raises
    RuntimeError with an actionable message if startup never called it —
    fails loudly at first use rather than a confusing AttributeError deep
    inside a request."""
    if _engine is None:
        raise RuntimeError(
            "no engine configured; call configure_engine(DATABASE_URL) at app startup "
            "before serving requests (or before running tests)."
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the async_sessionmaker configured by `configure_engine()`.
    Same fail-fast contract as `get_engine()`."""
    if _sessionmaker is None:
        raise RuntimeError(
            "no sessionmaker configured; call configure_engine(DATABASE_URL) at app "
            "startup before serving requests (or before running tests)."
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """The FastAPI dependency: yields one `AsyncSession` per request, with
    explicit commit/rollback/close discipline per
    references/backend/sqlalchemy.md's "Sessions & transactions" —

    - Success (no exception raised by the route/service code that ran with
      this session): commit.
    - Any exception: roll back, then re-raise (never swallowed) so the
      route's own error handling — or the error-envelope/ exception
      handler in Step 2 — still sees it.
    - Either way: close the session, guaranteed via `finally`, so a
      connection is never leaked back to the pool half-used.

    Takes no arguments deliberately — FastAPI's dependency injection calls
    it as `Depends(get_db)` with zero per-route wiring; the engine/
    sessionmaker it uses come from the module-level state `configure_engine()`
    set at startup, not from a parameter threaded through every route."""
    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _reset_engine_for_tests() -> None:
    """Test-only hook: clears the cached engine/sessionmaker between
    tests, so one test's `configure_engine()` call never leaks into the
    next. Not part of this module's public contract — mirrors
    secrets-loading's `_reset_asm_client_cache_for_tests()` pattern."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
