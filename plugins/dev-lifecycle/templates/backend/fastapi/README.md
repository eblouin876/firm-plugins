<!--
block: backend/fastapi
needs:
  - DATABASE_URL (required); JWT_SIGNING_KEY (required to use any /auth/* route — see "Auth" below); ENVIRONMENT/DEBUG/CORS_ALLOWED_ORIGINS/RATE_LIMIT_*/SECURITY_HEADERS_*/SECRETS_BACKEND (optional, secure defaults — see "Security composition" + docs/fragment.md)
  - port: 8000 (uvicorn default)
  - Python 3.13.x + uv (no committed uv.lock — see pyproject.toml)
exposes:
  - routes: GET/POST /items, GET/PATCH/DELETE /items/{id}, GET /health, GET /readyz, POST /auth/register|login|refresh|logout, GET /auth/me
  - the OpenAPI 3.1 contract (bearer security scheme) packages/api-client generates from
  - security composition: security-headers/request-id-audit/rate-limiting/CORS wired by default
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# backend/fastapi

The FastAPI backend block: async FastAPI + SQLAlchemy 2.0 + Postgres, built
on this catalog's locked backend components (error envelope, DB mixins,
async session, generic repository, pagination, settings) and, as of Stage 3
Step 3b (#26), the security-composition catalog (security headers, CORS
lockdown, rate limiting, secrets loading, audit logging, input validation).
Lives at `templates/backend/fastapi/` in this repo; scaffolding materializes
it into a project's `apps/api/`. Step 2 (issue #26, epic #22) built the app
skeleton, data layer, and contract endpoints; Step 3a hardened the vendored
import packaging; Step 3b (this update) vendors and wires the security
components. OpenAPI export + Dockerfile/compose (Step 4) is still out of
scope here, marked as a `TODO` comment at its seam (see app/main.py).

## Contents
- Composition contract
- Vendored components
- Security composition
- App layout
- Error contract
- Auth (Stage 5a, #41)
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
  `GET /readyz` (readiness, real `SELECT 1`), `POST /auth/register`,
  `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`,
  `GET /auth/me` — real behavior (Stage 5a, #41) against the vendored auth
  component's `AuthService`, not a stub — see "Auth" below.
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

**Security components (Stage 3 Step 3b, #26)** — the 6 baseline catalog
components under `templates/components/security/`, each landed as its own
subpackage under `app/core/security/`:

| Vendored into | Sourced from | Component README |
| --- | --- | --- |
| `app/core/security/security_headers/{_core,fastapi}.py` | `security-headers/{_core,fastapi}.py` | `templates/components/security/security-headers/README.md` |
| `app/core/security/cors_lockdown/{_core,fastapi}.py` | `cors-lockdown/{_core,fastapi}.py` | `templates/components/security/cors-lockdown/README.md` |
| `app/core/security/rate_limiting/{_core,fastapi}.py` | `rate-limiting/{_core,fastapi}.py` | `templates/components/security/rate-limiting/README.md` |
| `app/core/security/secret_store/secret_store.py` | `secrets-loading/secret_store.py` | `templates/components/security/secrets-loading/README.md` |
| `app/core/security/audit_logging/audit.py` | `audit-logging/audit.py` | `templates/components/security/audit-logging/README.md` |
| `app/core/security/input_validation/validation.py` | `input-validation/validation.py` | `templates/components/security/input-validation/README.md` |
| `app/core/security/auth/{_core,fastapi}.py` | `security/auth/{_core,fastapi}.py` | `templates/components/security/auth/README.md` |

**Auth (Stage 5a, #41)** vendors the same way — `_core.py`/`fastapi.py`
byte-copied (below each file's header note) into `app/core/security/auth/`,
plus an `__init__.py` re-export seam matching `security_headers/`'s. Unlike
the six baseline components above, this one also has app-specific glue
living in the SAME directory: `app/core/security/auth/stores.py`
(SQLAlchemy-backed `UserStore`/`RefreshTokenStore` implementations, the
`PasswordService`/`TokenService` construction) is **not** vendored — it
imports `app.models`/`app.core.config`, so the weekly freshness audit does
not touch it; see that file's own docstring.

`webhook-signature` and `idempotency` (also in the component catalog, under
`templates/components/security/`) are **deliberately not vendored** here —
both are payments-shaped concerns (verifying an inbound webhook's
signature; deduplicating a retried mutating request) with no consumer yet
in this block. The Stage 11 payments recipe vendors and wires them
alongside whatever payments endpoint actually needs them, rather than this
block guessing at that wiring ahead of time.

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
byte-identical.

**Step 3b's security components follow the same invariant.** Three of the
six (`security_headers`, `cors_lockdown`, `rate_limiting`) pair a `_core.py`
with a `fastapi.py` the source component ships importing via a bare
`import _core` (the same flat, directory-local sibling-import convention
`db-mixins`/`pagination` use); each `fastapi.py`'s import is rewritten to
`from . import _core` (package-relative), with a one-line `DRIFT:` header
note — the rest of each file, including every other `_core.<name>`
reference, is untouched. The other three (`secret_store`, `audit_logging`'s
`audit.py`, `input_validation`) ship as a single flat file with no
cross-import to adapt, so they stay byte-identical below their header —
they still land as their own subpackage directory (not a bare
`app/core/security/<file>.py` module) purely for a consistent,
self-contained-subpackage shape across `app/core/security/`, matching the
five components that do have a cross-import to isolate. Every subpackage's
`__init__.py` is new glue (not vendored), re-exporting that component's
public names the same way `app/core/db/__init__.py` does — see each
subpackage's own `__init__.py` docstring.

`app/core/security/audit_logging/middleware.py` is also new glue, not a
vendored file: `audit.py`'s own README documents `bind_request_id()`/
`reset_request_id()` as a hook "for Step 3 middleware" but ships no
middleware itself (the component is framework-neutral). This file is that
Step 3 middleware for FastAPI — see "Security composition" below.

## Security composition

Four of the six vendored security components are wired as middleware in
`app/main.py`'s `create_app()`; `secret_store` and `input_validation` are
library code composed at the point of use instead (see below). All four
middlewares are on by default — nothing to opt into.

**Middleware order, OUTERMOST -> INNERMOST (this order is load-bearing —
see the "why" after the table):**

| # | Middleware | Wraps | Why here |
| --- | --- | --- | --- |
| 1 | `security_headers.SecurityHeadersMiddleware` | everything | Runs last on the way OUT, so it sets/overwrites headers on every response any lower layer produces — a rate-limit 429, a CORS preflight reply, a routed handler's normal response — none of which can suppress these headers by building their own response object. **Exception:** the catch-all `Exception`/500 handler is pulled out by Starlette and run by `ServerErrorMiddleware`, OUTSIDE this middleware entirely — `app/main.py`'s handler stamps the identical `SecurityHeadersPolicy` output (and the bound `x-request-id`) onto that response directly, so the 500 still carries them, just not via this middleware. See `_make_unhandled_exception_handler`'s docstring in `app/main.py`. |
| 2 | `audit_logging.RequestIDMiddleware` | rate-limiting, CORS, routing | Binds the request id into `audit.py`'s contextvar BEFORE rate-limiting runs, so a rate-limit denial's own audit trail (today: none — a future stage that adds one gets the id automatically) and every downstream `audit_event()` call already carry it. |
| 3 | `rate_limiting.RateLimitMiddleware` | CORS, routing | Pre-auth (this app has no real authentication yet — Stage 5, #28), general per-client-IP ceiling. Runs OUTSIDE CORS deliberately: a cross-origin preflight `OPTIONS` still consumes rate-limit budget even though it never reaches CORS's own allow/deny decision, so an attacker can't use preflights to bypass the ceiling. |
| 4 (innermost) | `cors_lockdown.add_cors` (Starlette's own `CORSMiddleware`) | routing | Closest to the router/exception handlers. Deny-by-default — see below. |

**Why this order, mechanically:** Starlette's `add_middleware()` prepends
to its internal list and builds the runtime stack by iterating that list in
**reverse** (verified against this project's pinned Starlette:
`add_middleware` does `self.user_middleware.insert(0, ...)`;
`build_middleware_stack` does `for cls, ... in reversed(middleware): app =
cls(app, ...)`). The practical consequence `app/main.py`'s own comments
call out at each call site: the middleware added **last** ends up
**outermost**. `create_app()` therefore calls `add_cors()` first (call 1 of
4), then `RateLimitMiddleware`, then `RequestIDMiddleware`, then
`add_security_headers()` last (call 4 of 4) — the reverse of the
outermost-to-innermost table above.

**CORS: deny-by-default, wired conditionally.** `CORSPolicy.__init__`
itself refuses to construct with an empty `allow_origins` (see
`cors_lockdown/README.md`'s explicit-allowlist posture) — there is no "deny
everything" policy object to build. `create_app()` treats an empty
`cors_allowed_origins` (the secure default both `AppSettings` and this
project's `Settings` inherit) as "add no `CORSMiddleware` at all" rather
than trying to construct one: with no `CORSMiddleware` in the stack, no
`Access-Control-Allow-Origin` header is ever sent, so a browser blocks
every cross-origin JS request regardless — the same practical outcome as
an explicit empty-allowlist policy, without hitting `CORSPolicy`'s
construction-time guard on every dev/test boot where no origins are
configured yet. Set `CORS_ALLOWED_ORIGINS` (a JSON array in `.env`/env, per
`AppSettings`) to the exact origin(s) this environment's frontend is served
from to turn CORS on.

**Rate limiting: secure defaults, one in-memory store per app instance.**
`Settings.rate_limit_capacity` (default 60) / `rate_limit_refill_per_second`
(default 1.0) / `rate_limit_trusted_hops` (default **0** — distrust
`X-Forwarded-For` entirely, per `rate_limiting/_core.py`'s `client_ip_key`)
configure a single `InMemoryBucketStore` created per `create_app()` call,
constructed with `max_keys=50_000` — an explicit, bounded cap on top of the
store's own idle-eviction (`ttl_seconds`, default 900s), so a burst of
high-cardinality keys within one TTL window (e.g. a spoofed-IP flood) can't
grow the in-memory dict without bound; the store evicts the oldest-by-
last-seen bucket once the cap is hit. Per-process, like the component's own
README documents — a multi-worker/
multi-replica deployment gets a looser *effective* ceiling than the
configured numbers alone suggest; a Stage 11 Redis-backed `BucketStore`
closes that gap without either this wiring or the component's own code
changing (same `BucketStore` Protocol). Set `RATE_LIMIT_TRUSTED_HOPS` to
the exact number of trusted reverse proxies in front of this app, per
environment, once that topology is confirmed — never guessed, and never
left above 0 without confirming it (a wrong value lets a client spoof its
own rate-limit key via a forged header).

**Secrets composition (`secret_store`).** Not middleware — a library
`app/core/config.py`'s `Settings` composes directly, per the exact pattern
`app/core/settings.py`'s own module docstring documents (subclass
`AppSettings`, wire a field's `default_factory` to `secret_store.
get_secret(...)`). This block's one concrete example:
`Settings.jwt_signing_key`, resolved via `get_secret("JWT_SIGNING_KEY",
required=False)`. Still `required=False` at the `Settings()` construction
seam — a missing `JWT_SIGNING_KEY` must not fail app boot/import, since
most of this app's routes/tests never touch auth at all — but Stage 5a
(#41) now genuinely CONSUMES this field: `app/core/security/auth/
stores.py`'s `get_token_service()` is the fail-CLOSED check, refusing to
construct a `TokenService` (and therefore refusing every `/auth/*` route
that needs one) when `jwt_signing_key` is `None`, surfacing as a 500
`internal_error` envelope rather than ever signing/verifying a token with
an empty key. `SECRETS_BACKEND=aws-secrets-manager` (consulted directly by
`secret_store.py` from process env, independent of `Settings`) opts into
the AWS Secrets Manager fallback layer for this and any future
`get_secret()` call in this app — see `secrets-loading/README.md`'s
"Layered resolution".

**Input validation (`input_validation`).** Not middleware either —
`StrictModel` is the base `app/schemas/item.py`'s `ItemBase`/`ItemUpdate`
now extend, giving `ItemCreate`/`ItemUpdate`/`ItemOut` `extra="forbid"` +
`str_strip_whitespace` + `validate_assignment` + `strict=True` in place of
the earlier ad hoc `ConfigDict(extra="forbid")`. Item's own fields stay
plain `str`/`Field(min_length=..., max_length=...)` rather than adopting
`SafeText`/`ShortStr` — those add a `no_control_chars` check this generic
"widget name" exemplar has no documented need for; a real project's own
free-text fields (descriptions, comments) are where those types belong —
see `app/schemas/item.py`'s own module docstring.

**Not wired: `webhook_signature`, `idempotency`.** See "Vendored
components" above — both stay unvendored until the Stage 11 payments
recipe has an actual endpoint that needs them.

## App layout

```
app/
  main.py              # create_app() factory: routers, exception handlers, OpenAPI/bearer config
  api/
    deps.py             # get_auth_service (per-request AuthService) + get_current_principal
    routers/
      health.py          # /health (liveness), /readyz (readiness)
      items.py            # full CRUD, the contract exemplar
      auth.py              # /auth/register|login|refresh|logout|me — real (Stage 5a, #41)
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
    security/
      __init__.py                  # package marker (see its own docstring)
      security_headers/              # vendored _core.py + fastapi.py, __init__.py re-exports
      cors_lockdown/                 # vendored _core.py + fastapi.py, __init__.py re-exports
      rate_limiting/                 # vendored _core.py + fastapi.py, __init__.py re-exports
      secret_store/                  # vendored secret_store.py, __init__.py re-exports
      audit_logging/                 # vendored audit.py + NEW middleware.py (RequestIDMiddleware)
      input_validation/              # vendored validation.py, __init__.py re-exports
      auth/                          # vendored _core.py + fastapi.py, __init__.py re-exports; NEW stores.py (app code, not vendored)
  models/
    __init__.py            # aggregator: imports every model (Item, User, RefreshToken) so nothing is missed by migrations/tests
    item.py               # the Item ORM model (contract exemplar)
    user.py                 # the User ORM model (Stage 5a, #41)
    refresh_token.py          # the RefreshToken ORM model (Stage 5a, #41)
  schemas/
    item.py                # ItemCreate/ItemUpdate/ItemOut
    health.py                # HealthStatus/ReadinessStatus
    auth.py                    # RegisterRequest/LoginRequest/RefreshRequest/TokenResponse/PrincipalOut
alembic/                  # async env.py; 0001 (items), 0002 (users + refresh_tokens, Stage 5a #41)
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
500 `internal_error` envelope, never leaking `str(exc)` to the client — and
(Stage 3 Step 4 review fix) stamps the security headers and `x-request-id`
onto that response itself, since `ServerErrorMiddleware` (the Starlette
internal that serves this one handler) sits OUTSIDE every
`add_middleware()` layer this app registers — see
`_make_unhandled_exception_handler`'s docstring in `app/main.py` for the
mechanics, and "Security composition" above for the middleware order this
is an exception to.

The 422/404 shapes above are also what the exported OpenAPI schema
documents — see "OpenAPI export" next; without that fixup, FastAPI's
auto-generated schema would describe the native `HTTPValidationError` shape
for 422 instead of the `ErrorEnvelope` this app actually sends.

## OpenAPI export

`python -m app.export_openapi [output_path]` (writes to `output_path`, or
stdout if omitted) exports this block's OpenAPI 3.1 schema **without a live
database** — `app/export_openapi.py`'s `export_openapi_schema()` builds a
fresh app via `create_app()`'s `settings=` injection seam and calls
`.openapi()` directly, never starting an ASGI server or running `lifespan`
(the only place a real `DATABASE_URL` is ever touched). This is the
mechanism `packages/api-client` uses to keep its committed `openapi.json`
(and the client generated from it) in sync with what this block actually
serves — see that package's README's "Stage 3: the live schema" section.

`app/main.py`'s `create_app()` also installs `_install_error_envelope_openapi`,
which overrides `app.openapi()` (FastAPI's standard customization point) to
replace every operation's native `HTTPValidationError`-shaped 422 response
with `ErrorEnvelope` — the shape `_validation_exception_handler` actually
sends — and to drop `HTTPValidationError`/`ValidationError` from
`components/schemas` once nothing references them. `NotFoundError`'s 404 is
documented per-route instead (`responses={404: {"model": ErrorEnvelope}}`
on `app/api/routers/items.py`'s three ID-addressed routes), since only
those routes can actually 404. This fixup runs identically whether the
schema is served live at `/openapi.json` or exported via this script — both
paths call the same `app.openapi()`.

## Auth (Stage 5a, #41)

Real, end-to-end register/login/refresh/logout/me, wired against
`templates/components/security/auth/`'s framework-neutral `AuthService`
(Argon2id password hashing, HS256 JWT access/refresh tokens, refresh-token
rotation with reuse detection) — see that component's own `_core.py` for
the full state machine and `README.md` for the security rationale. This
block's job is purely the wiring: SQLAlchemy-backed `UserStore`/
`RefreshTokenStore` implementations (`app/core/security/auth/stores.py`,
against `app/models/user.py`'s `User` and `app/models/refresh_token.py`'s
`RefreshToken`), the per-request `AuthService` provider
(`app/api/deps.py:get_auth_service`), and the real route handlers
(`app/api/routers/auth.py`).

- `POST /auth/register` → `RegisterRequest{email,password}` → 201
  `PrincipalOut`. Duplicate normalized email → 409 `conflict`.
- `POST /auth/login` → `LoginRequest` → 200 `TokenResponse`. Bad
  credentials → 401 `unauthenticated` (identical for "no such account" and
  "wrong password" — see `_core.py`'s `InvalidCredentials` docstring on
  the user-enumeration defense).
- `POST /auth/refresh` → `RefreshRequest` → 200 `TokenResponse`, rotating
  the token. Invalid or REUSED → 401 `unauthenticated`, indistinguishable
  at the wire — a reuse event has, as a side effect, already revoked the
  entire token family in the DB by the time the 401 is returned (see
  `_core.py`'s `AuthService.refresh` docstring for the 6-step state
  machine, and `tests/test_auth.py`'s
  `test_refresh_token_reuse_is_detected_and_kills_the_whole_family` for
  the HTTP-level proof).
- `POST /auth/logout` → `RefreshRequest` → 204. Best-effort and idempotent
  — an already-invalid/unknown/revoked token still returns 204.
- `GET /auth/me` → bearer token via `get_current_principal` → 200
  `PrincipalOut`. Missing/invalid/expired/wrong-type (a refresh token
  presented here) → 401 `unauthenticated`.

Every `_core.AuthError` subclass raised by any handler is left uncaught in
`app/api/routers/auth.py` — `app/main.py`'s `create_app()` registers a
handler for the `AuthError` base class (catches every subclass via MRO
walk, including the vendored component's `InsufficientRole`) that renders
this app's `ErrorEnvelope` using the component's own `AUTH_ERROR_HTTP`
string-keyed status/code table (`app/core/security/auth/fastapi.py`) —
see `_auth_error_handler`'s own docstring in `app/main.py`.

**Fail-closed on missing config.** `app/core/security/auth/stores.py`'s
`get_token_service()` refuses to construct a `TokenService` — and
therefore refuses every `/auth/*` route — when `Settings.jwt_signing_key`
is unset, raising `AuthNotConfiguredError` (a plain `RuntimeError`, caught
by the generic catch-all `Exception` handler, rendering 500
`internal_error`) rather than ever signing/verifying with an empty key.
`PrincipalOut` stays `{id, email}` only in this stage — no `roles` on the
wire yet; the RBAC wire surface (`require_roles`, already present in the
vendored component's `fastapi.py`) is Stage 5d.

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
connection, just emitted SQL) modes. Two migrations exist today:
`0001_create_items_table.py` (`app/models/item.py`'s `Item`) and
`0002_create_auth_tables.py` (Stage 5a, #41 — `app/models/user.py`'s
`User` and `app/models/refresh_token.py`'s `RefreshToken`), both
hand-written to match their models column-for-column rather than
`--autogenerate`d.

**Verified against real PostgreSQL 16** (the sandbox's available
cluster) — `alembic upgrade head` ran online over `asyncpg`, and a
create-then-get `Item` round-tripped through the real, booted app over
that connection. **Gap:** this matrix pins PostgreSQL **18.x**
(`references/compatibility-matrix.md`'s Data row); the verification
sandbox only had a startable 16 cluster available. Nothing in this block's
schema or migration uses an 18-only feature, but a genuine 18 run has not
been performed — re-verify against 18 before treating this as a full
matrix-compliant proof.

### 0002 verification transcript (Stage 5a, #41)

Offline emission (`alembic upgrade 0001:0002 --sql`, no connection —
proves the migration is emittable without a live DB):

```sql
BEGIN;

-- Running upgrade 0001 -> 0002

CREATE TABLE users (
    id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE refresh_tokens (
    id UUID NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    jti VARCHAR(32) NOT NULL,
    family_id VARCHAR(32) NOT NULL,
    user_id UUID NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    revoked BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_refresh_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX ix_refresh_tokens_family_id ON refresh_tokens (family_id);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;
```

Online run against real PostgreSQL 16 (`alembic upgrade head` from a fresh
database — applies both 0001 and 0002 in one run):

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create items table
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, create auth tables
$ alembic current
0002 (head)
```

**Integration proof, over real HTTP against that same PG16 database** —
register → login → refresh (rotation) → replay the already-used refresh
token (reuse detection) → the rotated, never-reused tip is *also* rejected
afterward (whole-family revocation, not just the one reused token),
followed by a direct query of `refresh_tokens` proving `revoked = true` on
every row in the family:

```
== register ==
201 {'id': '44bb16da-9fc1-464a-af4b-5af1794fd455', 'email': 'pgverify@example.com'}
== login ==
200
== refresh (rotation 1) ==
200
== REPLAY the already-used original refresh token (reuse detection) ==
401 {'error': {'code': 'unauthenticated', 'message': 'Refresh token reuse detected -- the token family has been revoked.', 'details': None}}
== the rotated (never-reused) tip is ALSO now dead (whole family revoked) ==
401 {'error': {'code': 'unauthenticated', 'message': 'Refresh token has been revoked.', 'details': None}}
== users row ==
{'id': UUID('44bb16da-9fc1-464a-af4b-5af1794fd455'), 'email': 'pgverify@example.com'}
== refresh_tokens rows for this user ==
{'token_hash': 'cb4c47ba...', 'family_id': '3c03c9f29bee425bb5ffcfde0d8d2535', 'used_at': datetime(2026, 7, 23, 3, 22, 20, 586899, tzinfo=timezone.utc), 'revoked': True}
{'token_hash': '65de810c...', 'family_id': '3c03c9f29bee425bb5ffcfde0d8d2535', 'used_at': None, 'revoked': True}

DB PROOF: whole refresh-token family is revoked=True after reuse detection.
```

(Token hashes truncated above for readability; both rows share one
`family_id` and both are `revoked = True`, confirmed by a direct
`asyncpg` query against the `refresh_tokens` table — independent of the
HTTP response, which only proves the *client* saw 401.)

## Dev run (Docker)

`Dockerfile` + `docker-compose.yml` (this directory) boot this block for
local development — `just dev` (monorepo `justfile`) drives them for a
materialized project. Not a production deploy manifest — see each file's
own header comment; Stage 9's devops/infrastructure block owns real
deployment.

- **`Dockerfile`**: `python:3.13-slim-bookworm`, uv-installed (pinned via
  `ghcr.io/astral-sh/uv:0.11.31` — see `references/compatibility-matrix.md`'s
  "Containers" row), non-root `app` user, `uv sync --no-dev` (the `dev`
  dependency-group — pytest/httpx/aiosqlite — never lands in this image).
  `CMD` runs `uvicorn ... --reload`, matching the compose file's bind mounts.
- **`docker-compose.yml`**: a `db` service (`postgres:18-bookworm`, matrix-pinned,
  dev-only credentials) with a healthcheck, and an `api` service that waits
  on it, runs `alembic upgrade head`, then boots `uvicorn --reload` with
  `./app` and `./alembic` bind-mounted over the image's copied-in source
  for live reload. Run directly with `docker compose up --build` from this
  directory, or via `just dev` once materialized (see the justfile's own
  comment for how it detects a Python app).

## Testing

Hermetic integration tests (`tests/`, aiosqlite + `StaticPool`) exercise
the composed app end to end — app boot, `/health`/`/readyz`, item CRUD
round-trip, the `Page` envelope, the 422 remap (both a missing required
field and an `extra="forbid"` rejection), the enveloped 404, and the
bearer scheme's presence in `/openapi.json`. This block does **not**
duplicate each vendored component's own unit tests (`error-envelope/
tests/`, `repository/tests/`, ...) inside `app/` — see "Judgment calls"
for why.

`tests/test_auth.py` (Stage 5a, #41) exercises the real auth surface
against the hermetic client: register → login → me happy path (including
email normalization); duplicate register → 409; bad login → 401
(unknown email and wrong password, both indistinguishable); refresh
rotation; **refresh-token reuse detection, at the HTTP level, proving the
whole family is killed** (`test_refresh_token_reuse_is_detected_and_kills_the_whole_family`
— the crown-jewel test, see "Auth" above); logout → 204 then refresh →
401; logout idempotency; `/me` without/with-a-garbage/with-a-wrong-type
bearer token → 401; the fail-closed `AuthNotConfiguredError` path (no
`JWT_SIGNING_KEY` → 500, never signs with an empty key); and the bearer
scheme's continued presence in `/openapi.json`. Uses `make_client`
(bespoke `Settings(jwt_signing_key=...)`) rather than the plain `client`
fixture, since the latter's app is built from the process-wide
`get_settings()` singleton, which never has `JWT_SIGNING_KEY` set in the
test process's environment.

`tests/test_security_composition.py` (Stage 3 Step 3b, #26) proves the
security-composition wiring in `app/main.py`'s `create_app()` against real
request/response behavior: security headers present on a normal response
(and HSTS present only over an explicit `https://` request, absent over
plain `http`); CORS preflight allowing a configured origin, rejecting a
disallowed one, and not being wired at all when no origins are configured;
rate limiting returning 429 with `Retry-After` once a tiny configured burst
is exhausted, and that denial still carrying the outer middlewares' own
headers (`X-Request-ID`, security headers); request-id binding proven
directly against `RequestIDMiddleware` + `audit_event()` (a minted or
reflected `X-Request-ID`, a malformed inbound id replaced rather than
trusted, and the audit contextvar actually carrying the same id during the
request and unbound after); and `StrictModel`'s adoption in
`app/schemas/item.py` rejecting an unknown field on `PATCH` and a wrong
JSON type on `POST`, plus a standalone sanity check that the app's actual
imported `StrictModel` rejects a numeric string for an `int` field under
`strict=True` (Item's own fields are str-only, so that specific
strict-vs-lax behavior isn't otherwise observable over this block's HTTP
surface). Uses the `make_client` factory fixture (`tests/conftest.py`) to
build a bespoke `Settings()` per test rather than mutating process env
vars or sleeping in real time for the rate-limit burst.

Run: `uv run --python 3.13 --with fastapi --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with 'pydantic==2.13.*' --with pydantic-settings --with alembic --with httpx --with pytest --with pytest-asyncio --with 'pyjwt==2.13.*' --with 'argon2-cffi==25.1.*' -- pytest tests -q`

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
- **`GET /auth/me` does one extra direct `SqlAlchemyUserStore.get_by_id`
  lookup rather than adding a "fetch profile" method to `AuthService`.**
  `_core.AccessClaims` (what `get_current_principal` resolves a bearer
  token to) deliberately carries only `sub`/`roles`/`jti`/timestamps, not
  `email` — see that component's own `UserStore` Protocol docstring on why
  it's a storage seam for register/login/refresh, not a general lookup
  API. Adding a profile-fetch method to the LOCKED `_core.py` for one
  route's convenience was rejected in favor of this router doing its own
  narrow, explicit lookup.
- **`SqlAlchemyRefreshTokenStore.add`/`mark_used`/`revoke_family` each
  explicitly `commit()`, not just `flush()`.** `_core.py`'s own
  `RefreshTokenStore` Protocol docstring requires this durability
  ("Implementations MUST make add/mark_used/revoke_family durable
  (committed) before returning... so a concurrent second presentation of
  the just-rotated token sees the updated `used_at`") — under the default
  READ COMMITTED isolation, a `flush()` alone is invisible to a
  concurrently-racing second request until an actual `commit()`, which
  would defeat reuse detection under a genuine race. This intentionally
  commits mid-request, ahead of `get_db()`'s own end-of-request commit — a
  second `commit()` on an already-clean session is a harmless no-op.
- **`app.state.settings` is a new per-app-instance seam, not
  `Depends(get_settings)`.** `app/api/deps.py:get_auth_service` needs the
  EXACT `Settings` a given `create_app()` call was built with (its
  `jwt_signing_key` in particular) — not the separate, process-wide
  `lru_cache`d `get_settings()` singleton every OTHER piece of security
  composition (rate limiting, CORS, security headers) reads directly at
  app-construction time. `tests/conftest.py`'s `make_client` fixture
  relies on exactly this seam to configure a bespoke `jwt_signing_key` per
  test without mutating process env vars, which would leak across tests.
- **sqlite's `DateTime(timezone=True)` round-trips as timezone-NAIVE, not
  aware — normalized back to UTC-aware at the store boundary
  (`app/core/security/auth/stores.py`'s `_as_utc`).** PostgreSQL's
  `timestamptz` always comes back tz-aware; sqlite (this app's hermetic
  test dialect) has no native timezone-aware datetime type and silently
  drops the offset on read. `_core.AuthService.refresh` compares
  `row.expires_at <= self._now()`, and `self._now()` is always tz-aware —
  comparing aware and naive raises `TypeError` under sqlite without this
  normalization (a real, hermetic-test-breaking bug discovered while
  implementing Stage 5a, fixed at the store layer, not in the locked
  `_core.py`).
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
- **`create_app()` now resolves `Settings()` at app-CONSTRUCTION time, not
  only inside `lifespan` (Stage 3 Step 3b, #26).** Step 2's `lifespan`
  deliberately deferred `get_settings()` to ASGI-startup time specifically
  so a missing `DATABASE_URL` wouldn't fail at plain module import (letting
  tooling introspect the app/schema without a real database configured).
  Wiring CORS/rate-limiting/security-header config from `Settings` requires
  a `Settings` instance at the point `create_app()` builds the middleware
  stack, which now runs at import time too (`app = create_app()` at this
  module's bottom) — so that specific "import never needs `DATABASE_URL`"
  guarantee no longer holds. Judged an acceptable, intentional narrowing
  (fail-fast now happens even earlier — at construction — rather than
  later, at first request), not a regression, and it's the common
  FastAPI pattern of constructing settings at module scope. `create_app()`
  gained a `settings:` override parameter as the escape hatch tooling/tests
  need instead — see its own docstring and `tests/conftest.py`'s
  `make_client` fixture.
- **Rate limiting wraps CORS, not the other way around.** The middleware-
  order table under "Security composition" states this; the reason is
  narrower than "arbitrary but documented": a cross-origin preflight
  `OPTIONS` request still consumes rate-limit budget under this order even
  though it never reaches CORS's own allow/deny decision, closing off using
  preflights specifically to burn through the ceiling for free. The
  alternative order (CORS outside rate-limiting) would let an attacker send
  unlimited preflights from a disallowed origin at zero rate-limit cost,
  since CORS would reject them before rate-limiting ever saw them.
- **`jwt_signing_key` is `required=False` with no fallback value, not
  `required=True` with no default (`AppSettings`' own usual "no default
  means required" convention) — even now that Stage 5a (#41) genuinely
  consumes it.** Making it required would fail `Settings()` construction —
  happening at app-construction/import time, see above — for every test
  and dev boot that never touches auth (most of them), none of which set
  `JWT_SIGNING_KEY`. A hard-coded insecure-but-non-empty fallback was
  considered and rejected: this issue's own instructions say "don't invent
  secrets," and a fabricated default value is exactly that, even labeled
  "dev-only" — the risk of it silently surviving into a real deployment
  isn't worth avoiding an `Optional[str]` return type here. The actual
  fail-CLOSED enforcement lives one layer up instead, at the point auth is
  actually used — see "Auth" above's "Fail-closed on missing config."
- **`X-Request-ID`, if client-supplied, is trusted and reflected (bounded to
  a short, printable-ASCII, no-control-character shape) rather than always
  minted fresh.** This is deliberately a DIFFERENT trust posture than
  rate-limiting's `X-Forwarded-For` handling: a request-id is a correlation
  id for tracing, not a security/access decision, so reflecting a
  caller-supplied value back is safe and useful (a client can correlate its
  own logs with this app's). It's still attacker-influenced input reaching
  a response header and every `audit_event()` in the request, so it's
  shape-validated (`audit_logging/middleware.py`'s `_SAFE_REQUEST_ID_RE`)
  before being trusted — a value that doesn't match gets a freshly minted
  `uuid4` instead of a "sanitized" version of the bad one.
- **No API-boundary field in this block's own schemas demonstrates
  `StrictModel`'s strict-mode numeric-coercion rejection.** `Item`'s fields
  are all `str`/`str | None` — Pydantic already rejects a JSON number for a
  `str` field even in lax (non-strict) mode, so POSTing `{"name": 123}`
  doesn't isolate what `strict=True` specifically adds over the old ad hoc
  `ConfigDict(extra="forbid")`. Adding an `int`/`bool` field to `Item`
  purely to exercise this would be exactly the over-refactoring this step's
  instructions warn against for a generic exemplar model. Resolved by
  pairing an API-boundary test (wrong JSON type, still meaningful) with one
  direct, non-API test against this app's actual imported `StrictModel`
  class proving the numeric-string-for-`int` rejection — see
  `tests/test_security_composition.py`'s
  `test_strict_model_rejects_numeric_string_for_an_int_field`.
