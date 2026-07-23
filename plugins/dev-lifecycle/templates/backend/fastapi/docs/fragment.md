<!-- fragment: block:backend/fastapi -->

## Setup
Materializes into `apps/api/`. Requires Python 3.13.x + uv (`uv sync
--all-groups`) and a `DATABASE_URL` naming an async driver
(`postgresql+asyncpg://...` in dev/prod, `sqlite+aiosqlite://` in
hermetic tests — see `app/core/settings.py`). Run migrations with
`uv run alembic upgrade head`, then serve with
`uv run uvicorn app.main:app --port 8000` — or `just dev` /
`docker compose up --build` (this directory's `Dockerfile` +
`docker-compose.yml`) to boot the API against a real Postgres without a
local Python install. `GET /health` is the liveness probe (no DB);
`GET /readyz` is readiness (`SELECT 1`). Full CRUD lives at `/items`; real
auth (Stage 5a, #41) lives at `/auth/register|login|refresh|logout|me`,
against the vendored auth component's Argon2id + JWT + refresh-rotation
`AuthService` — set `JWT_SIGNING_KEY` before using any of them (see
"Secrets" below; unset fails closed at 500, never signs with an empty
key). Stage 5c (#45) adds `/auth/verify-email|request-password-reset|
reset-password` against the vendored `AccountService`, plus a per-account
`LockoutPolicy` — `login` now REQUIRES a verified email by default
(`AUTH_REQUIRE_EMAIL_VERIFICATION`, default `true`) and locks an account
after `AUTH_LOCKOUT_MAX_FAILURES` (default 5) consecutive wrong passwords
within `AUTH_LOCKOUT_WINDOW_SECONDS` (default 900s); see the block
README's "Account lifecycle" section for the full endpoint/policy detail.
Verify/reset emails go through `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/
`SMTP_PASSWORD`/`EMAIL_FROM` when `SMTP_HOST` is set, else the dev-only
`ConsoleEmailSender` (logs the message, including the raw token, instead
of delivering it — never construct it in a real deployment).
`python -m app.export_openapi` exports that schema without a live
database — the mechanism `packages/api-client`'s `client-generate` recipe
uses. Optional config, all with secure defaults:
`RATE_LIMIT_CAPACITY` (60) / `RATE_LIMIT_REFILL_PER_SECOND` (1.0) /
`RATE_LIMIT_TRUSTED_HOPS` (0 — distrust `X-Forwarded-For`; set to the exact
trusted reverse-proxy hop count per environment),
`SECURITY_HEADERS_HSTS_PRELOAD` (false), `CORS_ALLOWED_ORIGINS` (`[]` —
CORS is unwired entirely until set).

## Security composition
Wired by default in `app/main.py`'s `create_app()`, outermost to innermost:
security-headers (CSP/HSTS-when-https/nosniff/frame-deny on every
response) -> request-id/audit binding (`X-Request-ID` minted or reflected,
bound into `audit.py`'s contextvar) -> rate-limiting (per-client-IP token
bucket, 429 + `Retry-After` on deny) -> CORS (Starlette's `CORSMiddleware`,
deny-by-default — unwired entirely unless `CORS_ALLOWED_ORIGINS` is set,
never a wildcard). `input_validation.StrictModel` is the base for
`ItemCreate`/`ItemUpdate`/`ItemOut` (`app/schemas/item.py`) — unknown
fields and lax-mode type coercion are both rejected at the API boundary.
`webhook_signature`/`idempotency` (also in the security catalog) are
**not** vendored here — the Stage 11 payments recipe wires them against an
actual webhook endpoint. Full rationale: this block's README.md's
"Security composition" section.

## Secrets
| `DATABASE_URL` | backend/fastapi | Required, no default — the async-driver connection string both the app (`app/main.py`'s lifespan) and Alembic (`alembic/env.py`) read from this project's `Settings`. |
| `JWT_SIGNING_KEY` | backend/fastapi | Required to use any `/auth/*` route (Stage 5a, #41) — resolved via `secret_store.get_secret("JWT_SIGNING_KEY", required=False)` (`app/core/config.py`'s `Settings.jwt_signing_key`, `repr=False`/`exclude=True` so it never appears in a `Settings` repr/dump). Still optional at `Settings()` construction (`None` until set — most routes/tests never touch auth); `app/core/security/auth/stores.py:get_token_service()` is where a missing value fails CLOSED (500 `internal_error`), at the point auth is actually used. |
| `SECRETS_BACKEND` | backend/fastapi | Optional, default env-only. Set to `aws-secrets-manager` to enable `secret_store`'s AWS Secrets Manager fallback layer for `JWT_SIGNING_KEY` and any future `get_secret()` call in this app — read directly from process env by `secret_store.py`, independent of `Settings`. See `secrets-loading/README.md`'s "Layered resolution". |

## Maintenance
`app/core/{errors,settings}.py`, `app/core/db/{mixins,session,
repository,query,schema}.py`, and (Stage 3 Step 3b, #26)
`app/core/security/{security_headers,cors_lockdown,rate_limiting,
secret_store,audit_logging,input_validation}/`, plus (Stage 5a, #41)
`app/core/security/auth/{_core,fastapi}.py`, are byte-copies (below each
file's header note) of this catalog's locked backend/security components,
kept in sync via the weekly freshness audit (Stage 12, #35) — never
hand-edit below a vendored file's header note; edit the source component
and re-sync instead. `app/core/security/auth/stores.py` (SQLAlchemy store
implementations, `PasswordService`/`TokenService` construction) lives in
that same directory but is NOT vendored — it imports `app.models`, so it's
ordinary app code the freshness audit does not touch. Seven subpackages'
worth of vendored security code, plus new (non-vendored) glue — `app/core/
security/audit_logging/middleware.py` (request-id binding), each
subpackage's `__init__.py` (relative-import re-export seams, same pattern
as `app/core/db/__init__.py`), and `auth/stores.py` above — see the block
README's "Vendored components", "Security composition", and "Auth"
sections for the full drift/wiring detail. Step 4 added the OpenAPI export
(`app/export_openapi.py`), the `ErrorEnvelope`-accurate schema fixup
(`app/main.py`'s `_install_error_envelope_openapi`), and the dev
Dockerfile/compose run path. Stage 5a (#41) added `User`/`RefreshToken`
models + Alembic `0002`, real `/auth/*` behavior, and extended the frozen
contract (`packages/api-client/openapi.json`) + regenerated client — see
the block README's "OpenAPI export", "Dev run (Docker)", "Auth", and
"Database & migrations" sections. Stage 5c (#45) added `SingleUseToken`/
`LoginAttempt` models + `User.email_verified`/`verified_at` + Alembic
`0003`, the vendored `AccountService`/`LockoutPolicy` wiring, the three
new `/auth/*` routes, and again extended the frozen contract + client —
see the README's "Account lifecycle" subsection and its "0003 verification
transcript". Verified online against PostgreSQL 16 (the pinned matrix
target is 18.x — re-verify against 18 before treating this as a full
matrix-compliant proof).
