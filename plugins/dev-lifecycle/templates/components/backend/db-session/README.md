<!--
block: components/backend/db-session  # catalog component
needs:
  - SQLAlchemy 2.0.x (async extras): the sole runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row
  - DATABASE_URL: an async-driver connection string (e.g. postgresql+asyncpg://... in prod, sqlite+aiosqlite:// in tests) passed to configure_engine()
exposes:
  - configure_engine(database_url, *, echo=False, **engine_kwargs) -> AsyncEngine — call once at app startup; fails fast (ValueError) on a bare sync-driver scheme (postgresql://, sqlite://, mysql://)
  - get_engine() / get_sessionmaker() — accessors, raise RuntimeError if configure_engine() was never called
  - get_db() -> AsyncIterator[AsyncSession] — the FastAPI dependency (Depends(get_db)); commit-on-success, rollback-on-exception, always closes
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# db-session

A framework-neutral-*within-SQLAlchemy* drop-in `session.py`: an async
engine factory built from a `DATABASE_URL`, an `async_sessionmaker`, and a
`get_db` dependency shaped for FastAPI's `Depends()` — one `AsyncSession`
per request, with explicit commit/rollback/close discipline. Lives at
`templates/components/backend/db-session/` in this repo; Stage 3 backend
blocks copy `session.py` verbatim into `app/core/db/session.py`. Embodies
`references/backend/sqlalchemy.md`'s "Sessions & transactions" section.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block.

**SQLAlchemy-specific — Django cannot reuse this file.** Django's ORM owns
its own connection/transaction model (per-request autocommit, or explicit
`transaction.atomic()` blocks) with no `AsyncEngine`/`AsyncSession`/
`async_sessionmaker` equivalent; Stage 4's Django track does not reuse
this file.

## Contents
- Composition contract
- One engine, configured once at startup
- Fail-fast on a non-async driver
- get_db: the commit/rollback/close contract
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **SQLAlchemy 2.0.x with the `asyncio` extra** — pinned per
  `references/compatibility-matrix.md`'s Backend — Python row. An async
  driver (`asyncpg` for PostgreSQL in prod, `aiosqlite` for tests) must be
  installed and match the `DATABASE_URL` scheme
  (`postgresql+asyncpg://...`, `sqlite+aiosqlite://...`) — see
  `references/backend/sqlalchemy.md`'s version-check note on matching the
  driver to the engine's sync/async mode.
- **`DATABASE_URL`** — passed to `configure_engine()`, not read from the
  environment by this module itself (that's `settings/`'s job — see
  "One engine, configured once at startup" below).

**EXPOSES**
- `configure_engine(database_url, *, echo=False, **engine_kwargs) ->
  AsyncEngine` — builds and caches (module-level) the engine and its
  `async_sessionmaker`. Call exactly once, at app startup.
- `get_engine()` / `get_sessionmaker()` — accessors; each raises a clear
  `RuntimeError` if `configure_engine()` was never called, rather than a
  confusing `AttributeError`/`NoneType` failure deep inside a request.
- `get_db() -> AsyncIterator[AsyncSession]` — the FastAPI dependency
  (`Depends(get_db)`). Yields one session per request; commits on success,
  rolls back and re-raises on any exception, always closes.
- Its co-located doc fragment: `docs/fragment.md`.

Keep this file alongside `mixins.py` and `repository.py` (also
SQLAlchemy-specific) in the same `app/core/db/` directory when copied in —
`repository.py`'s `AsyncRepository` is constructed with a session this
module's `get_db` supplies.

## One engine, configured once at startup

`get_db` takes **no arguments** — FastAPI wires it as `Depends(get_db)`
with zero per-route boilerplate. That's possible because the engine and
sessionmaker it uses live in this module's own cached state, set once by
`configure_engine(database_url)` at app startup (a FastAPI lifespan
handler or `on_startup` hook), typically fed from `settings/`'s
`DATABASE_URL` field:

```python
from session import configure_engine

@app.on_event("startup")
async def startup() -> None:
    configure_engine(settings.database_url)
```

`pool_pre_ping=True` is set by default (overridable via `engine_kwargs`)
so a connection the DB server already dropped (idle timeout, failover) is
recycled transparently instead of surfacing a stale-connection error on
the next request.

## Fail-fast on a non-async driver

`configure_engine()` checks `database_url`'s scheme before calling
`create_async_engine()`. A bare synchronous scheme this catalog's own
dialects would otherwise recognize — `postgresql://`, `postgres://`,
`sqlite://`, `mysql://` — raises `ValueError` immediately, naming the
async driver to use instead:

```
DATABASE_URL 'postgresql://user:pass@localhost/db' uses the synchronous
'postgresql://' scheme, but configure_engine() requires an async driver —
use 'postgresql+asyncpg://' instead (e.g.
'postgresql+asyncpg://user:pass@host/dbname'). Install the matching async
driver package if it isn't already a dependency.
```

Without this check, a misconfigured `DATABASE_URL` (a config value pasted
from a sync-context example, an env var typo) still reaches
`create_async_engine`, which either fails later — at the first query — or
raises an import error for a sync driver package the project never
installed, several frames deep and far from the actual mistake. The check
only recognizes schemes this catalog targets; an already-async scheme
(anything with a `+driver` suffix, e.g. `postgresql+asyncpg`) always
passes through untouched, and a scheme this catalog has no opinion about
is left to `create_async_engine`'s own error.

## get_db: the commit/rollback/close contract

```python
session = session_factory()
try:
    yield session
    await session.commit()
except Exception:
    await session.rollback()
    raise
finally:
    await session.close()
```

- **Success** (the route/service code that ran with this session raised
  nothing): commit.
- **Any exception**: roll back, then **re-raise** — never swallowed, so
  the route's own error handling (or the `error-envelope/` exception
  handler wired in Step 2) still sees it.
- **Either way**: close, guaranteed via `finally` — a connection is never
  leaked back to the pool half-used. Deliberately *not* wrapped in `async
  with session_factory() as session:` in addition to the explicit
  `finally` close — that combination double-closes the session (harmless
  functionally, since `close()` is idempotent, but redundant and it
  muddies a test asserting "closed exactly once"); this module manages
  the session's lifetime explicitly instead.

## Testing

`tests/test_session.py` covers: `configure_engine`/`get_engine`/
`get_sessionmaker` round-tripping against an in-memory sqlite engine
(via `aiosqlite` + `StaticPool` so the "in-memory" database is shared
across the pool's connections, the standard pattern for a hermetic
async-sqlite test), both accessors raising a clear `RuntimeError` before
`configure_engine()` has run, `get_db()` yielding a real `AsyncSession`,
the commit-on-success path (a row added through `get_db()` is visible from
a fresh session afterward), the rollback-on-exception path (a row added
then an exception thrown into the generator leaves no row persisted), the
original exception propagating unchanged (not swallowed or replaced), the
session's `close()` being called exactly once on both the success and the
exception path (verified via a monkeypatched spy on `AsyncSession.close`),
`configure_engine` rejecting a bare `postgresql://`/`sqlite://`/`mysql://`
scheme with a `ValueError` naming the correct async driver, the rejection
message quoting the offending URL, a rejected call leaving the
already-configured engine untouched (no partial/clobbered state), and an
already-async scheme (`sqlite+aiosqlite://`) passing the guard without
raising.

Run: `uv run --python 3.13 --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with pytest --with pytest-asyncio -- pytest templates/components/backend/db-session/tests/ -q`
(async tests use explicit `@pytest.mark.asyncio` markers — pytest-asyncio's
default "strict" mode picks them up with no extra `--asyncio-mode` flag or
ini configuration needed).

## Judgment calls

- **Module-level cached engine/sessionmaker, not a class or a dependency-
  injected config object.** Mirrors `secrets-loading`'s
  `_get_asm_client()` caching pattern in this same catalog — a drop-in
  single-file module with no app-framework object to hang state off of.
  `configure_engine()`/`_reset_engine_for_tests()` are the two seams that
  make this pattern testable without a real app running.
- **No `async with session_factory() as session:` wrapping the explicit
  try/finally.** Using both closes the session twice per request (see
  above) — functionally harmless but redundant; this module picks the
  explicit form and documents it so a future edit doesn't "helpfully"
  re-add the context manager and reintroduce the double close.
- **`get_db()` re-raises rather than translating the exception.** Mapping
  a raised exception to an HTTP response is `error-envelope/`'s and Step
  2's FastAPI exception-handler's job, not this module's — `get_db()`'s
  only contract is "the DB transaction reflects what actually happened,"
  independent of how that outcome eventually reaches the client.
- **The async-driver guard is a small, hardcoded scheme map, not a
  general URL-parsing/validation library.** `_ASYNC_DRIVER_HINT` only
  covers the dialects this catalog actually targets (postgresql, sqlite,
  plus mysql as a common fourth); an unrecognized scheme is left to
  `create_async_engine`'s own error rather than this module trying to be
  exhaustive about every SQLAlchemy dialect that exists.
- **The guard checks the scheme, not whether the named async driver
  package is actually installed.** Confirming the driver is importable
  would require actually attempting the import (or a package-name lookup
  keyed to the dialect) — more machinery than a fail-fast scheme check
  needs; a missing driver package still surfaces its own clear
  `ModuleNotFoundError` from `create_async_engine`, just not this
  module's more specific message.
