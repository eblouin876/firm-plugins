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

## Maintenance
`core/contract/{errors,pagination,secret_store}.py` are byte-copies (below
each file's header note) of this catalog's locked `error-envelope`/
`pagination`/`secrets-loading` components — kept in sync via the weekly
freshness audit (Stage 12, #35); `pagination.py` is a deliberate subset
(drops the SQLAlchemy-only `PageResult`, see its own `DRIFT:` header line),
so re-syncing it needs the trim re-applied by hand, not a straight copy.
`core/models.py`'s `Item` (UUID PK, `created_at`/`updated_at`, soft-delete
via `deleted_at` + a partial index + a default-manager scope) is this
step's own app code, matching `backend/fastapi`'s `Item` field-for-field —
see the block README's "The Item model". No DRF views/serializers/router,
exception handler, or pagination-class wiring exists yet — that is a later
step's scope (see "Conformance" above and the block README's own section
of the same name).
