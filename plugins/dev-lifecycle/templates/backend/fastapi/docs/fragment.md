<!-- fragment: block:backend/fastapi -->

## Setup
Materializes into `apps/api/`. Requires Python 3.13.x + uv (`uv sync
--all-groups`) and a `DATABASE_URL` naming an async driver
(`postgresql+asyncpg://...` in dev/prod, `sqlite+aiosqlite://` in
hermetic tests — see `app/core/settings.py`). Run migrations with
`uv run alembic upgrade head`, then serve with
`uv run uvicorn app.main:app --port 8000`. `GET /health` is the liveness
probe (no DB); `GET /readyz` is readiness (`SELECT 1`). Full CRUD lives at
`/items`; `/auth/login`, `/auth/refresh`, `/auth/me` are Stage-5 stubs
(501) with their schemas and the `HTTPBearer` scheme already locked into
`/openapi.json`.

## Secrets
| `DATABASE_URL` | backend/fastapi | Required, no default — the async-driver connection string both the app (`app/main.py`'s lifespan) and Alembic (`alembic/env.py`) read from this project's `Settings`. |

## Maintenance
`app/core/{errors,settings}.py` and `app/core/db/{mixins,session,
repository,query,schema}.py` are byte-copies of this catalog's locked
backend components, kept in sync via the weekly freshness audit (Stage 12,
#35) — never hand-edit below a vendored file's header note; edit the
source component and re-sync instead. CORS/security-header middleware is
Step 3's job (not yet wired — see the `TODO` in `app/main.py`); OpenAPI
export and the Dockerfile/compose deploy path are Step 4's. Verified
online against PostgreSQL 16 (the pinned matrix target is 18.x — re-verify
against 18 before treating this as a full matrix-compliant proof).
