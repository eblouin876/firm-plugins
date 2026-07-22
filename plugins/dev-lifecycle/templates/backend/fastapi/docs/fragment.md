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
`GET /readyz` is readiness (`SELECT 1`). Full CRUD lives at `/items`;
`/auth/login`, `/auth/refresh`, `/auth/me` are Stage-5 stubs (501) with
their schemas and the `HTTPBearer` scheme already locked into
`/openapi.json`. `python -m app.export_openapi` exports that schema
without a live database — the mechanism `packages/api-client`'s
`client-generate` recipe uses. Optional config, all with secure defaults:
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
| `JWT_SIGNING_KEY` | backend/fastapi | Optional, unused until Stage 5 (#28) wires real JWT issuance — resolved via `secret_store.get_secret("JWT_SIGNING_KEY", required=False)` (`app/core/config.py`'s `Settings.jwt_signing_key`, `repr=False`/`exclude=True` so it never appears in a `Settings` repr/dump). No fallback value is invented; `None` until a project sets it. |
| `SECRETS_BACKEND` | backend/fastapi | Optional, default env-only. Set to `aws-secrets-manager` to enable `secret_store`'s AWS Secrets Manager fallback layer for `JWT_SIGNING_KEY` and any future `get_secret()` call in this app — read directly from process env by `secret_store.py`, independent of `Settings`. See `secrets-loading/README.md`'s "Layered resolution". |

## Maintenance
`app/core/{errors,settings}.py`, `app/core/db/{mixins,session,
repository,query,schema}.py`, and (Stage 3 Step 3b, #26)
`app/core/security/{security_headers,cors_lockdown,rate_limiting,
secret_store,audit_logging,input_validation}/` are byte-copies (below each
file's header note) of this catalog's locked backend/security components,
kept in sync via the weekly freshness audit (Stage 12, #35) — never
hand-edit below a vendored file's header note; edit the source component
and re-sync instead. Six subpackages' worth of vendored security code, plus
two pieces of new (non-vendored) glue — `app/core/security/audit_logging/
middleware.py` (request-id binding) and each subpackage's `__init__.py`
(relative-import re-export seams, same pattern as `app/core/db/
__init__.py`) — landed in Step 3b; see the block README's "Vendored
components" and "Security composition" sections for the full drift/wiring
detail. Step 4 (this update) added the OpenAPI export
(`app/export_openapi.py`), the `ErrorEnvelope`-accurate schema fixup
(`app/main.py`'s `_install_error_envelope_openapi`), and the dev
Dockerfile/compose run path — see the block README's "OpenAPI export" and
"Dev run (Docker)" sections. Verified online against PostgreSQL 16 (the
pinned matrix target is 18.x — re-verify against 18 before treating this
as a full matrix-compliant proof).
