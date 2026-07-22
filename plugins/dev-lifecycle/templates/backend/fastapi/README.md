<!--
block: backend/fastapi
needs:
  - DATABASE_URL: async-driver scheme (postgresql+asyncpg:// prod, sqlite+aiosqlite:// tests) — see app/core/settings.py, app/core/db/session.py
  - env vars: DATABASE_URL (required), ENVIRONMENT/DEBUG/CORS_ALLOWED_ORIGINS (optional)
  - port: 8000 (uvicorn default)
  - Python 3.13.x + uv (no committed uv.lock — see pyproject.toml)
exposes:
  - routes: GET/POST /items, GET/PATCH/DELETE /items/{id}, GET /health, GET /readyz, POST /auth/login|refresh (stub), GET /auth/me (stub)
  - the OpenAPI 3.1 contract (bearer security scheme) packages/api-client generates from
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# backend/fastapi

The FastAPI backend block: async FastAPI + SQLAlchemy 2.0 + Postgres, built
on this catalog's locked backend components (error envelope, DB mixins,
async session, generic repository, pagination, settings). Lives at
`templates/backend/fastapi/` in this repo; scaffolding materializes it
into a project's `apps/api/`. This is Stage 3's Step 2 (issue #26, epic
#22) — the app skeleton, data layer, and contract endpoints. Security-
component vendoring (CORS, security headers, rate limiting) is Step 3;
OpenAPI export + Dockerfile/compose is Step 4 — both explicitly out of
scope here, marked as `TODO` comments at their seams (see app/main.py).

## Contents
- Composition contract
- Vendored components
- App layout
- Error contract
- Auth stubs (Stage 5 seam)
- Pagination
- Database & migrations
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **A Postgres database in prod, sqlite in hermetic tests** — reached via
  `DATABASE_URL`, an async-driver connection string
  (`postgresql+asyncpg://...` / `sqlite+aiosqlite://`). Required, no
  default — a missing `DATABASE_URL` fails `Settings()` construction at
  app startup (see `app/core/settings.py`'s vendored `AppSettings`), not on
  the first request that touches the database.
- **Env vars** — `DATABASE_URL` (required); `ENVIRONMENT`
  (`development`/`test`/`staging`/`production`, default `development`),
  `DEBUG` (default `false`), `CORS_ALLOWED_ORIGINS` (default `[]`, unused
  until Step 3 wires CORS middleware) — all inherited from the vendored
  `AppSettings`.
- **Port 8000** — the uvicorn default this block assumes
  (`uvicorn app.main:app --port 8000`).
- **Python 3.13.x, uv-managed** — `uv sync` installs the pinned deps from
  `pyproject.toml`; no `uv.lock` is committed in this template (see
  "Judgment calls").

**EXPOSES**
- **Routes**: `GET/POST /items`, `GET/PATCH/DELETE /items/{id}` (full CRUD
  over the `Item` contract exemplar), `GET /health` (liveness, no DB),
  `GET /readyz` (readiness, real `SELECT 1`), `POST /auth/login`,
  `POST /auth/refresh`, `GET /auth/me` (all three: defined contract, stub
  501 body — see "Auth stubs" below).
- **The OpenAPI 3.1 contract** `packages/api-client` generates from —
  title, version, the `HTTPBearer` security scheme (auto-registered by
  `app/api/deps.py`'s `get_current_principal` stub dependency). Step 4
  points `orval.config.ts`'s `input.target` at this app's live
  `/openapi.json` instead of the current sample fixture
  (`packages/api-client/openapi.sample.json`) — see that package's README,
  "Stage 3: swapping in the live schema".
- **Port 8000**.
- **Its co-located doc fragment**: `docs/fragment.md`.

## Vendored components

`app/` contains **byte-copies** (plus a short header note) of six locked
catalog components under `templates/components/backend/` — the app tree
does not re-derive or reimplement any of their logic:

| Vendored into | Sourced from | Component README |
| --- | --- | --- |
| `app/core/errors.py` | `error-envelope/errors.py` | `templates/components/backend/error-envelope/README.md` |
| `app/core/settings.py` | `settings/settings.py` | `templates/components/backend/settings/README.md` |
| `app/core/db/mixins.py` | `db-mixins/mixins.py` | `templates/components/backend/db-mixins/README.md` |
| `app/core/db/session.py` | `db-session/session.py` | `templates/components/backend/db-session/README.md` |
| `app/core/db/repository.py` | `repository/repository.py` | `templates/components/backend/repository/README.md` |
| `app/core/db/query.py` | `pagination/query.py` | `templates/components/backend/pagination/README.md` |
| `app/core/db/schema.py` | `pagination/schema.py` | `templates/components/backend/pagination/README.md` |

Security components (secrets-loading, input-validation, etc., under
`templates/components/security/`) are **not** vendored yet — that's Step
3's job, per this issue's scope split.

**Kept in sync via the weekly freshness audit** (Stage 12, #35): each
vendored file's header note names its source path; the audit diffs the
vendored copy (below the header) against the current source and flags
drift. Don't hand-edit a vendored file's logic directly — edit the source
component, then re-sync the copy.

**INVARIANT (Stage 3 #26, Step 3a): each vendored component lands as a
self-contained subpackage using relative imports — never a global
`sys.path` manipulation.** The component catalog's own `db-mixins`/
`db-session`/`repository`/`pagination` sources use flat, directory-local
sibling imports (`from schema import ...`, `from query import ...`) so a
project can vendor just one directory with no package-path assumptions
(see each component's own README). Composed into a real app package,
though, that convention would need *something* to put the directory on
`sys.path` to resolve — and doing that once, process-wide, exposes generic
module names (`schema`, `query`) as top-level imports any other in-process
package could collide with silently. Instead, vendoring into this app
REWRITES those bare sibling imports to package-relative ones
(`from .schema import ...`, `from .query import ...`) in the two files
that have them (`app/core/db/query.py`, `app/core/db/repository.py`) —
each carries a `DRIFT:` header line noting the adaptation, since this
means those two files are no longer byte-identical to their
component-catalog source below the header. `app/core/db/mixins.py`,
`session.py`, and `schema.py` have no cross-imports to adapt and stay
byte-identical. Step 3b's security components follow the same invariant:
each one copied into `app/core/security/<name>/` as its own subpackage,
relative imports only, no `sys.path.insert` anywhere in the app.

## App layout

```
app/
  main.py              # create_app() factory: routers, exception handlers, OpenAPI/bearer config
  api/
    deps.py             # get_current_principal — the Stage 5 auth seam
    routers/
      health.py          # /health (liveness), /readyz (readiness)
      items.py            # full CRUD, the contract exemplar
      auth.py              # /auth/login, /auth/refresh, /auth/me — stub 501s
  core/
    config.py            # this project's Settings(AppSettings) + get_settings()
    settings.py           # vendored AppSettings (see table above)
    errors.py              # vendored ErrorEnvelope/AppError hierarchy
    db/
      __init__.py           # package seam: relative-import re-exports (see its own docstring)
      mixins.py               # vendored Base/UUIDPrimaryKey/TimestampMixin/SoftDeleteMixin
      session.py                # vendored configure_engine/get_db
      repository.py              # vendored AsyncRepository
      query.py                    # vendored paginate_select
      schema.py                    # vendored PageParams/Page/PageResult
  models/
    __init__.py            # aggregator: imports every model (Item today) so nothing is missed by migrations/tests
    item.py               # the Item ORM model (contract exemplar)
  schemas/
    item.py                # ItemCreate/ItemUpdate/ItemOut
    health.py                # HealthStatus/ReadinessStatus
    auth.py                    # LoginRequest/RefreshRequest/TokenResponse/PrincipalOut
alembic/                  # async env.py, one initial migration (items table)
tests/                   # hermetic integration tests (see "Testing")
docs/
  fragment.md              # this block's machine-parseable doc fragment (see documentation-standard.md)
```

`app/core/db/__init__.py` is the one piece of this tree that is **not** a
vendored file — it's new glue. The five SQLAlchemy-specific vendored files
in that directory (`mixins.py`, `session.py`, `repository.py`, `query.py`,
`schema.py`) are authored in the component catalog as flat, directory-local
drop-ins (`repository.py` imports `from query import paginate_select`;
`query.py` imports `from schema import ...` — not package-relative). This
app REWRITES those two files' cross-imports to package-relative
(`from .query import paginate_select`; `from .schema import ...`) rather
than putting the directory on `sys.path`, per the "Vendored components"
invariant above — `app/core/db/__init__.py` then just imports from its
relatively-importing siblings and re-exports the names the rest of the app
needs (`from app.core.db import Base, get_db, AsyncRepository, Page,
PageParams, PageResult`). See that file's own docstring and "Judgment
calls" below.

## Error contract

Every error response uses `app/core/errors.py`'s `ErrorEnvelope`
(`{"error": {"code", "message", "details"}}`), including FastAPI's own
request-boundary validation failures: `app/main.py` registers a
`RequestValidationError` handler that remaps FastAPI's native
`{"detail": [...]}` 422 shape into the envelope
(`code="validation_failed"`), exactly as error-envelope/README.md's "ONE
error shape — including the native 422" section requires. A second handler
catches every `AppError` subclass (`NotFoundError` -> 404,
`ConflictError` -> 409, ...) and renders `exc.to_envelope()` with
`exc.status_code`. A third, broader `Exception` handler (a judgment call —
see below) catches anything neither of those catches and renders a generic
500 `internal_error` envelope, never leaking `str(exc)` to the client.

## Auth stubs (Stage 5 seam)

`/auth/login`, `/auth/refresh`, `/auth/me` are gate-1 "define+stub":
request/response schemas (`app/schemas/auth.py`) and the `HTTPBearer`
security scheme (`app/api/deps.py`'s `get_current_principal`, used as a
dependency on `/auth/me`) are real and locked into the OpenAPI contract
now. Every handler body raises a plain `HTTPException(501)` — deliberately
**not** the `ErrorEnvelope` (`ErrorCode` is a closed, versioned enum with
no `not_implemented` member; adding one is a contract change out of scope
for this step — see `app/api/routers/auth.py`'s module docstring). Stage 5
(#28) replaces the bodies with real credential verification, JWT issuance,
and principal resolution.

## Pagination

`GET /items` returns `Page[ItemOut]`
(`{items, total, page, size, pages}`), built in the route handler from
`AsyncRepository.list()`'s internal `PageResult` via `Page.create(...)` —
never returned directly, per `repository/README.md`'s "Wire vs internal"
contract. Query params: `page` (1-indexed, default 1), `size` (default 20,
max 200) — an out-of-range value is a 422, not a silently clamped/ignored
value.

## Database & migrations

`alembic/` is async (`env.py` uses `async_engine_from_config` /
`connection.run_sync`), reads `DATABASE_URL` through this project's own
`Settings` (the same object `app/main.py`'s lifespan uses — one source of
truth for both), and supports both online (`alembic upgrade head`, a real
asyncpg connection) and offline (`alembic upgrade head --sql`, no
connection, just emitted SQL) modes. One migration exists today
(`0001_create_items_table.py`), hand-written to match `app/models/item.py`
column-for-column rather than `--autogenerate`d.

**Verified against real PostgreSQL 16** (the sandbox's available
cluster) — `alembic upgrade head` ran online over `asyncpg`, and a
create-then-get `Item` round-tripped through the real, booted app over
that connection. **Gap:** this matrix pins PostgreSQL **18.x**
(`references/compatibility-matrix.md`'s Data row); the verification
sandbox only had a startable 16 cluster available. Nothing in this block's
schema or migration uses an 18-only feature, but a genuine 18 run has not
been performed — re-verify against 18 before treating this as a full
matrix-compliant proof.

## Testing

Hermetic integration tests (`tests/`, aiosqlite + `StaticPool`) exercise
the composed app end to end — app boot, `/health`/`/readyz`, item CRUD
round-trip, the `Page` envelope, the 422 remap (both a missing required
field and an `extra="forbid"` rejection), the enveloped 404, the bearer
scheme's presence in `/openapi.json`, and all three auth stubs' 501s. This
block does **not** duplicate each vendored component's own unit tests
(`error-envelope/tests/`, `repository/tests/`, ...) inside `app/` — see
"Judgment calls" for why.

Run: `uv run --python 3.13 --with fastapi --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with 'pydantic==2.13.*' --with pydantic-settings --with alembic --with httpx --with pytest --with pytest-asyncio -- pytest tests -q`

Or, once materialized into a project: `uv sync --all-groups && uv run pytest`.

## Judgment calls

- **Vendored files land at `app/core/{errors,settings}.py` and
  `app/core/db/{mixins,session,repository,query,schema}.py`, not the Step
  2 task brief's illustrative `app/db/{base,mixins,session,repository}.py`
  / `app/schemas/{pagination,errors}.py` example paths.** Every vendored
  component's own module docstring and README already specify its
  drop-in target (`app/core/errors.py`, `app/core/settings.py`,
  `app/core/db/mixins.py` alongside `session.py`/`repository.py`/
  pagination's two files) — following those exactly, rather than the
  task brief's "e.g.", keeps this block consistent with what every other
  future backend block copying the same components will do, and avoids a
  split-brain "two documented target paths" problem for the freshness
  audit.
- **`app/core/db/__init__.py` is new glue, not a vendored byte-copy.**
  Originally (Step 2) it put its own directory on `sys.path` so the
  vendored files' flat sibling imports (`from query import ...`, `from
  schema import ...` — deliberately not package-relative in the component
  catalog itself, see each component's own README) would resolve unmodified.
  **Step 3a (#26) replaced that with the opposite approach**: rewrite
  `query.py`'s and `repository.py`'s cross-imports to package-relative
  (`from .schema import ...`, `from .query import ...`) instead, so
  `__init__.py` needs no `sys.path` manipulation at all. The sys.path
  approach was reconsidered because it makes generic module names
  (`schema`, `query`) importable as TOP-LEVEL, process-wide modules — a
  silent collision risk once Step 3b vendors security components as
  further siblings. Relative imports cost losing byte-identity on the two
  touched files (documented via each one's `DRIFT:` header line) but close
  that seam entirely; see "Vendored components" above for the resulting
  invariant every future vendored subpackage in this app follows.
- **Auth stubs return a plain `HTTPException(501)`, not an
  `ErrorEnvelope`.** See "Auth stubs" above — `ErrorCode` is locked, and
  adding a member for a temporary stub is a bigger contract decision than
  Step 2 should make unilaterally.
- **A third, broader `Exception` handler was added beyond the two Step 2
  explicitly asks for.** `error-envelope/errors.py`'s own module docstring
  describes an unhandled bug as something "the framework's generic 500
  handler still catches, mapping to this same base's `to_envelope()`" —
  without a catch-all handler that promise isn't actually true (FastAPI's
  raw default 500 would leak through unenveloped). Cheap to add, keeps the
  envelope contract literally universal; flagged here in case a reviewer
  wants it scoped differently.
- **No `uv.lock` committed.** Per this issue's own instructions — `uv
  sync` resolves the pinned `pyproject.toml` ranges freshly per project;
  a template block isn't a deployable unit with its own lockfile, the
  *materialized project* is.
- **Hermetic tests live once, at `tests/`, exercising the whole composed
  app — not duplicated per vendored component.** Each vendored component
  already ships its own unit test suite at its source location
  (`templates/components/backend/*/tests/`), covered by that component's
  own `README.md`/CI. Re-running those same unit tests inside every block
  that vendors them would multiply test-maintenance cost for zero added
  coverage; this block's own tests instead cover what's unique to it —
  the actual composition (routes + repository + pagination + error
  handlers wired together), which no single component's unit tests can
  exercise alone.
- **PostgreSQL 16, not the matrix's pinned 18.x, for the real-DB
  verification.** See "Database & migrations" above — the sandbox only had
  a startable 16 cluster; nothing in this block's schema is 18-specific,
  but this is a noted gap, not a substitute for an eventual 18 run.
