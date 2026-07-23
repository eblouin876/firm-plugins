<!-- fragment: block:backend/django -->

## Setup
Materializes into `apps/api/`, as an **alternative** to `backend/fastapi` in
the same slot — a project runs one backend track, not both. Requires
Python 3.13.x + uv (`uv sync --all-groups`), a `DATABASE_URL` naming a
Postgres connection (`postgres://...`, parsed by `dj-database-url`), and a
`SECRET_KEY` (required, no default — generate with `python -c "from
django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`).
Run migrations with `uv run python manage.py migrate`, check the project
with `uv run python manage.py check`. Hermetic checks needing no real
database server use `DJANGO_SETTINGS_MODULE=config.settings_test` (Django's
stdlib sqlite3 backend). As of Stage 4 Step 1 (#27), this block ships the
`Item` model + initial migration and the vendored contract sources only —
no HTTP routes are wired yet (`config/urls.py`'s `urlpatterns` is empty);
see the block README's "Conformance" section for what a later step adds.

## Conformance
Gate-1 decision: this track targets **wire-contract identity** with
`backend/fastapi` (byte-identical paths/methods/status/JSON), best-effort
OpenAPI `operationId`/component-name parity, and documented Django-only
client regeneration — not a promise that `backend/fastapi`'s exact
committed generated client is a drop-in replacement once a project swaps
tracks. Full rationale: the block README's "Conformance" section.

## Secrets
| `SECRET_KEY` | backend/django | Required, no default — `config/settings.py` raises at import time if unset. Never hardcoded; generate per environment. |
| `DATABASE_URL` | backend/django | Required, no default — a `postgres://` connection string parsed via `dj-database-url`. `config/settings_test.py` overrides to hermetic sqlite for checks/tests needing no real server. |
| `CORS_ALLOWED_ORIGINS` | backend/django | Optional, comma-separated. Empty/unset means NO cross-origin request is ever allowed (deny-by-default) — see `config/settings.py`'s "CORS" section and the block README's "Security composition". Not a secret value itself, but env-driven per this block's composition contract. |
| `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUSTED_HOPS` | backend/django | Optional — fall back to the rate-limiting component's own defaults (60, 1.0, 0) when unset. `RATE_LIMIT_TRUSTED_HOPS` MUST be set deliberately, per-environment, to the exact number of trusted proxies in front of this app — never guessed (see `core/security/rate_limiting/_core.py`'s `client_ip_key` docstring). |
| `JWT_SIGNING_KEY` | backend/django | Optional (`required=False`, no invented default) — resolved via `core.contract.secret_store.get_secret`, the composition seam for Stage 5's (#28) real authentication. Unconsumed as of this step; never logged. |

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
