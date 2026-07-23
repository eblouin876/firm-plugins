<!-- fragment: block:backend/django -->

## Setup
Materializes into `apps/api/`, as an **alternative** to `backend/fastapi` in
the same slot — a project runs one backend track, not both. Requires
Python 3.13.x + uv (`uv sync --all-groups`), a `DATABASE_URL` naming a
Postgres connection (`postgres://...`, parsed by `dj-database-url`), and a
`SECRET_KEY` (required, no default — generate with `python -c "from
django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`).
Run migrations with `uv run python manage.py migrate`, then serve with
`uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000` — or
`just dev` / `docker compose up --build` (this directory's `Dockerfile` +
`docker-compose.yml`, materializing to the same `apps/api/
docker-compose.yml` slot `backend/fastapi` uses) to boot the API against a
real Postgres without a local Python install. Hermetic checks needing no
real database server use `DJANGO_SETTINGS_MODULE=config.settings_test`
(Django's stdlib sqlite3 backend). `GET /health` is the liveness probe (no
DB, never rate-limited); `GET /readyz` is readiness (`SELECT 1`, also
never rate-limited). Full CRUD lives at `/items`. `/auth/register`,
`/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me` (Stage 5b, #44)
are real handlers against the vendored auth component
(`core/security/auth/`, Argon2id password hashing + HS256 JWT access/
refresh pairs with rotation-with-reuse-detection) — register 201 / login
200 / refresh 200 (rotates; reusing an already-rotated token 401s AND
revokes the whole token family) / logout 204 (idempotent) / me 200, with
the `HTTPBearer` scheme locked into `/api/schema`. Needs `JWT_SIGNING_KEY`
set (see "Secrets" below) — unset, every `/auth/*` route fails closed to
500, never signs a token with an empty key. Stage 5c (#45) adds
`/auth/verify-email|request-password-reset|reset-password` against the
vendored `AccountService`, plus a per-account `LockoutPolicy` —
`login` now REQUIRES a verified email by default
(`AUTH_REQUIRE_EMAIL_VERIFICATION`, default `True`) and locks an account
after `AUTH_LOCKOUT_MAX_FAILURES` (default 5) consecutive wrong passwords
within `AUTH_LOCKOUT_WINDOW_SECONDS` (default 900s); see the block
README's "Conformance / Account lifecycle + lockout" section for the full
endpoint/policy detail. Verify/reset emails go through Django's own
pluggable `EMAIL_BACKEND` (`DjangoEmailSender`, fire-and-forget/
non-raising) — `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/
`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS`/`EMAIL_FROM` when a real backend is
configured, else the dev-only console backend (logs the message,
including the raw token, instead of delivering it — never use it in a
real deployment). `manage.py spectacular
--format openapi-json --file <path>` exports that schema without a live
database. Optional config, all with secure defaults:
`RATE_LIMIT_CAPACITY` (60) / `RATE_LIMIT_REFILL_PER_SECOND` (1.0) /
`RATE_LIMIT_TRUSTED_HOPS` (0) / `RATE_LIMIT_MAX_KEYS` (50000),
`CORS_ALLOWED_ORIGINS` (`[]` — CORS is deny-by-default until set).

## Conformance
Gate-1 decision: this track targets **wire-contract identity** with
`backend/fastapi` (byte-identical paths/methods/status/JSON), best-effort
OpenAPI `operationId`/component-name parity, and documented Django-only
client regeneration — not a promise that `backend/fastapi`'s exact
committed generated client is a drop-in replacement once a project swaps
tracks. Full rationale: the block README's "Conformance" section.

**Stage 4 Step 4 (#27) delivered the PROOF; Stage 5b (#44) extended it to
full `/auth/*` parity for the original five auth operations; Stage 5c
(#45) extended it again for the three new account-lifecycle
operations**: `tests/test_schema_conformance.py` loads both this block's
drf-spectacular-generated schema and the frozen `packages/api-client/
openapi.json`, normalizes each documented operation's request/response
JSON Schema, and asserts the wire surfaces are EQUAL — 15/15 documented
(path, method) operations match (7 non-auth plus all eight `/auth/*`
operations, `_PENDING_PARITY_OPS` empty), with exactly one further,
individually-documented exception (a discovered nullability gap in the
frozen contract's own `ItemUpdate.name`/`update_item`, not mirrored into
this block — see that test file's own `_KNOWN_DIVERGENCES` and the block
README's "Step 4" section) — no auth-specific divergence was needed,
Stage 5c included. OperationIds match the frozen contract exactly (set by
hand per view); component names match 15 of 18 (the rest are
drf-spectacular's own naming conventions for enums/pagination-envelopes/
PATCH variants — see the README's parity table).

## Secrets
| `SECRET_KEY` | backend/django | Required, no default — `config/settings.py` raises at import time if unset. Never hardcoded; generate per environment. |
| `DATABASE_URL` | backend/django | Required, no default — a `postgres://` connection string parsed via `dj-database-url`. `config/settings_test.py` overrides to hermetic sqlite for checks/tests needing no real server. |
| `CORS_ALLOWED_ORIGINS` | backend/django | Optional, comma-separated. Empty/unset means NO cross-origin request is ever allowed (deny-by-default) — see `config/settings.py`'s "CORS" section and the block README's "Security composition". Not a secret value itself, but env-driven per this block's composition contract. |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUSTED_HOPS` / `RATE_LIMIT_MAX_KEYS` | backend/django | Optional — fall back to defaults (60, 1.0, 0, 50000) when unset. `RATE_LIMIT_TRUSTED_HOPS` MUST be set deliberately, per-environment, to the exact number of trusted proxies in front of this app — never guessed (see `core/security/rate_limiting/_core.py`'s `client_ip_key` docstring). `/health`/`/readyz` are exempt from rate limiting entirely regardless of these values (Stage 4 review fix, #27). |
| `JWT_SIGNING_KEY` | backend/django | Optional (`required=False`, no invented default) — resolved via `core.contract.secret_store.get_secret`. Consumed by `core.security.auth.stores.get_token_service()` (Stage 5b, #44): unset/empty fails every `/auth/*` route CLOSED with a 500 `internal_error` (`AuthNotConfiguredError`), never a token signed with an empty key. Never logged. `JWT_ISSUER`/`JWT_ACCESS_TTL_SECONDS`/`JWT_REFRESH_TTL_SECONDS` are the accompanying, non-secret env vars (defaults `"app"`/`900`/`1209600`, matching `backend/fastapi`'s identical fields). |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | backend/django | Optional (`required=False`), resolved via `core.contract.secret_store.get_secret` — same layered-resolution posture as `JWT_SIGNING_KEY`. Unset (`config/settings.py`'s default `EMAIL_BACKEND`, Django's own console backend) means verify/reset emails are only LOGGED, including the raw token — fine for dev/test, never acceptable in a real deployment where `AUTH_REQUIRE_EMAIL_VERIFICATION=True` (the default). Set alongside the non-secret `EMAIL_PORT`/`EMAIL_USE_TLS`/`EMAIL_FROM`/`EMAIL_BACKEND` before serving real traffic (Stage 5c, #45). |
| `AUTH_REQUIRE_EMAIL_VERIFICATION` / `AUTH_LOCKOUT_ENABLED` / `AUTH_LOCKOUT_MAX_FAILURES` / `AUTH_LOCKOUT_DURATION_SECONDS` / `AUTH_LOCKOUT_WINDOW_SECONDS` | backend/django | Optional, non-secret — secure defaults (`True`/`True`/`5`/`900`/`900`). Consumed by `core/views.py`'s `_build_login_auth_service()` (Stage 5c, #45): gates `LoginView` on a verified email and a per-account failed-login lockout. |
| `FRONTEND_BASE_URL` / `AUTH_VERIFY_TTL_SECONDS` / `AUTH_RESET_TTL_SECONDS` | backend/django | Optional, non-secret — defaults `http://localhost:5173`/`86400`/`3600`. Consumed by `core.security.auth.stores.build_account_service()` (Stage 5c, #45) to build the verify-email/reset-password links (`{FRONTEND_BASE_URL}/verify-email#token=...` / `.../reset-password#token=...`, the raw token in the URL FRAGMENT, never a query string — see `_core.AccountService`'s own docstring) and bound how long each issued token stays valid. |

## Maintenance
`core/contract/{errors,pagination,secret_store}.py` are byte-copies (below
each file's header note) of this catalog's locked `error-envelope`/
`pagination`/`secrets-loading` components — kept in sync via the weekly
freshness audit (Stage 12, #35); `pagination.py` is a deliberate subset
(drops the SQLAlchemy-only `PageResult`, see its own `DRIFT:` header line),
so re-syncing it needs the trim re-applied by hand, not a straight copy.
`secret_store.py` is NOT re-vendored a second time under `core/security/`
(Stage 4 Step 3, #27) — the Step 1 copy here is reused directly for the
`JWT_SIGNING_KEY` composition seam; see the block README's "Judgment calls"
for the dedup rationale.

`core/security/{security_headers,cors_lockdown,rate_limiting}/{_core,django}.py`
and `core/security/audit_logging/audit.py` (Stage 4 Step 3, #27) are the
same kind of byte-copy, below each file's header note, of this catalog's
locked `security-headers`/`cors-lockdown`/`rate-limiting`/`audit-logging`
components — kept in sync via the same weekly freshness audit.
`core/security/*/django.py` carry a one-line documented `DRIFT:` (a bare
`import _core` rewritten to the package-relative `from . import _core`),
matching `backend/fastapi`'s own vendoring convention.
`core/security/audit_logging/middleware.py` is NEW glue, not vendored — the
Django-track request-id/audit-bind middleware, mirroring
`backend/fastapi`'s equivalent for that track.
`core/security/input_validation/validation.py` is also a byte-copy of the
`input-validation` component, vendored but not yet called from anywhere in
this block (see the block README's "Judgment calls").

`core/models.py`'s `Item` (UUID PK, `created_at`/`updated_at`, soft-delete
via `deleted_at` + a partial index + a default-manager scope) is Step 2's
own app code, matching `backend/fastapi`'s `Item` field-for-field — see the
block README's "The Item model". The MIDDLEWARE stack
(`config/settings.py`) is this step's (Step 3's) own wiring — see the block
README's "Security composition" for the full order and rationale.

Stage 5c (#45) added `core.models.User.email_verified`/`verified_at` +
`SingleUseToken`/`LoginAttempt` models + migration `0003`,
`DjangoSingleUseTokenStore`/`DjangoLockoutStore`/`DjangoEmailSender`/
`AuditAuthEventSink` + the `build_lockout_policy`/`build_account_service`
factories (`core/security/auth/stores.py` — app code, NOT vendored, same
reason `build_auth_service()` already isn't), `core/views.py`'s
`_build_login_auth_service()` (the login verification+lockout+audit
gate) and its three new `VerifyEmailView`/`RequestPasswordResetView`/
`ResetPasswordView` views + matching `core/serializers.py` serializers,
and again extended the frozen contract (`packages/api-client/
openapi.json`) parity target — see the block README's "Conformance /
Account lifecycle + lockout (Stage 5c, #45)" and "Database & migrations"
sections.
