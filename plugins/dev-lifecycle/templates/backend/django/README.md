<!--
block: backend/django
needs:
  - DATABASE_URL (required, postgres:// scheme); SECRET_KEY (required, no default); DEBUG/ALLOWED_HOSTS (optional, secure defaults — see "Composition contract" + docs/fragment.md)
  - port: 8000 (uvicorn/gunicorn default, matching backend/fastapi)
  - Python 3.13.x + uv (no committed uv.lock — see pyproject.toml)
exposes:
  - the Item model + the DRF contract-emission layer (routes, serializers, ErrorEnvelope exception handler, Page paginator) — see "Conformance"
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-23
provenance: manual
-->

# backend/django

The Django + DRF backend block: Django 5.2 LTS + Django REST Framework +
Postgres via psycopg, built as an **ALTERNATIVE** to `backend/fastapi` in the
same `apps/api/` materialization slot (a project picks one backend track,
not both). Lives at `templates/backend/django/` in this repo; scaffolding
materializes it into a project's `apps/api/`, exactly like the FastAPI block
does. Stage 4 (#27, epic #22) in two steps: Step 1 shipped the project
skeleton, env-driven settings, the `Item` contract-exemplar model + initial
migration, and the two vendored contract sources (`error-envelope`,
`pagination`); **Step 2 (this state) is DRF contract-EMISSION** — the
routes/serializers, the custom `EXCEPTION_HANDLER`, and the pagination
class that actually render those vendored contracts over HTTP, reproducing
`backend/fastapi`'s wire shape — see "Conformance" below.

## Contents
- Composition contract
- Vendored contract sources
- App layout
- The Item model
- Conformance (Step 1 vs. Step 2)
- Security
- Database & migrations
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **A Postgres database**, reached via `DATABASE_URL` (`postgres://...` /
  `postgresql://...`, parsed by `dj-database-url` in `config/settings.py`).
  Required, no default — a missing `DATABASE_URL` raises at settings-module
  import time (`config/settings.py`'s own guard), not on the first request
  that touches the database. Hermetic checks/tests that need no real server
  use `config/settings_test.py` instead (`DJANGO_SETTINGS_MODULE=
  config.settings_test`), which overrides `DATABASES` to Django's stdlib
  sqlite3 backend — Django's equivalent of backend/fastapi's aiosqlite
  hermetic-test posture, no extra driver needed.
- **`SECRET_KEY`** — required, no default, **never hardcoded** (per this
  step's own instructions). Read directly from `os.environ["SECRET_KEY"]`;
  a missing value raises `RuntimeError` at settings-module import with a
  pointer to generate one.
- **`DEBUG`** (default `false` — the safe default, not Django's own
  `startproject` scaffold, which defaults `True`) and **`ALLOWED_HOSTS`**
  (default `[]`, comma-separated env var) — both env-driven, no code change
  needed per environment.
- **Port 8000** — matching `backend/fastapi`'s own default, so a project
  swapping tracks doesn't also have to change its port assumption.
- **Python 3.13.x, uv-managed** — `uv sync --all-groups` installs the
  pinned deps from `pyproject.toml`; no `uv.lock` is committed (see
  "Judgment calls").

**EXPOSES** (as of this step)
- The `Item` model (`core/models.py`) and its initial migration
  (`core/migrations/0001_initial.py`), verified against real PostgreSQL —
  see "Database & migrations".
- `core/contract/` — the vendored `ErrorEnvelope`/`AppError` hierarchy and
  `PageParams`/`Page` shapes THE contract every future route in this block
  conforms to (see "Vendored contract sources").
- No HTTP routes yet: `config/urls.py`'s `urlpatterns` is empty, with a
  `TODO` marking Step 2's DRF router seam. No OpenAPI schema is served yet
  either, even though `drf-spectacular` is installed and in
  `INSTALLED_APPS` — no `SPECTACULAR_SETTINGS`/schema view is wired.
- Its co-located doc fragment: `docs/fragment.md`.

## Vendored contract sources

`core/contract/` contains **byte-copies** (plus a short header note) of the
two locked catalog components this block's later steps reproduce the wire
shape of — the same "THE contract" sources `backend/fastapi` vendors, minus
the FastAPI/SQLAlchemy-specific parts neither applies to Django:

| Vendored into | Sourced from | Component README |
| --- | --- | --- |
| `core/contract/errors.py` | `error-envelope/errors.py` | `templates/components/backend/error-envelope/README.md` |
| `core/contract/pagination.py` | `pagination/schema.py` (PageParams+Page only — `PageResult` dropped, see file header) | `templates/components/backend/pagination/README.md` |
| `core/contract/secret_store.py` | `secrets-loading/secret_store.py` | `templates/components/security/secrets-loading/README.md` |

`errors.py` and `secret_store.py` are **byte-identical** below their header
(both are framework-neutral with no cross-imports to adapt — see each
file's own header). `pagination.py` is **not** byte-identical: it drops
`PageResult`, the SQLAlchemy-repository-only internal container that
`schema.py`'s own module docstring says "a Django project (Stage 4) copies
schema.py alone — in practice, only its `PageParams`/`Page` shapes matter
there; `PageResult` is SQLAlchemy-repository plumbing a Django view has no
use for" — see `pagination.py`'s own `DRIFT:` header line for the exact
diff.

`core/contract/__init__.py` is **new glue, not vendored** — a package seam
re-exporting each vendored file's public names, the same pattern
`backend/fastapi`'s `app/core/db/__init__.py` uses for its own vendored
subpackage.

**Kept in sync via the weekly freshness audit** (Stage 12, #35): each
vendored file's header note names its source path; the audit diffs the
vendored copy (below the header) against the current source and flags
drift. Don't hand-edit a vendored file's logic directly — edit the source
component, then re-sync the copy (re-applying the `pagination.py` trim by
hand, since that file is a deliberate subset, not a straight copy).

## App layout

```
manage.py                # Django's management entrypoint
pyproject.toml            # pinned deps — see references/compatibility-matrix.md's "Backend — Django track" + the new psycopg row
config/
  settings.py              # env-driven Settings: SECRET_KEY/DEBUG/ALLOWED_HOSTS/DATABASE_URL, REST_FRAMEWORK (EXCEPTION_HANDLER + DEFAULT_PAGINATION_CLASS wired)
  settings_test.py          # hermetic sqlite override for `manage.py check`/pytest — no real DB server needed
  urls.py                    # root URLconf — delegates to core.urls
  asgi.py                     # ASGI entrypoint (uvicorn)
  wsgi.py                      # WSGI entrypoint (gunicorn)
core/                    # the Django app (INSTALLED_APPS label: "core")
  models.py                # Item model + ItemManager/ItemQuerySet (soft-delete scoping)
  serializers.py             # ItemOut/ItemCreate/ItemUpdate + health/auth-stub serializers
  views.py                    # ItemViewSet + health/readyz + auth-stub views
  urls.py                      # DRF router (trailing_slash=False) + explicit health/readyz/auth paths
  exceptions.py                 # custom EXCEPTION_HANDLER -> ErrorEnvelope
  pagination.py                  # custom PageNumberPagination -> {items,total,page,size,pages}
  apps.py                   # CoreConfig
  migrations/
    0001_initial.py           # hand-verified-generated initial migration (see "Database & migrations")
  contract/                 # vendored contract sources — see "Vendored contract sources"
    errors.py
    pagination.py
    secret_store.py
tests/                   # conformance-proof suite — see "Testing"
docs/
  fragment.md              # this block's machine-parseable doc fragment (see documentation-standard.md)
```

## The Item model

`core/models.py`'s `Item` matches `backend/fastapi`'s `app/models/item.py`
field-for-field: `id` (UUID, `default=uuid.uuid4`, primary key),
`created_at` (`auto_now_add`), `updated_at` (`auto_now`), `deleted_at`
(nullable, `NULL` = not deleted), `name`/`description`. It is the Django-ORM
counterpart to `templates/components/backend/db-mixins/mixins.py`'s
`UUIDPrimaryKey`/`TimestampMixin`/`SoftDeleteMixin` — that component's own
module docstring says explicitly: "a Django backend (Stage 4) does NOT
reuse this file; it reaches for Django's own `models.UUIDField`,
`auto_now_add`/`auto_now`, and a custom soft-delete manager instead." This
model is that reach — not a vendored file, this step's own app code.

**Soft-delete scoping**: `Item.objects` (the default manager) is
`ItemManager`, built on `ItemQuerySet.not_deleted()` — every default lookup
(`Item.objects.all()`, `.get()`, `.filter()`) already excludes rows with a
non-null `deleted_at`, mirroring `SoftDeleteMixin.not_deleted()`'s `WHERE`
fragment for the SQLAlchemy track. `Item.all_objects` (Django's plain,
unscoped `models.Manager()`) and `Item.objects.with_deleted()` are the
escape hatches for the rare caller that needs soft-deleted rows too.

**Partial index**: `Meta.indexes` declares a partial B-tree index on
`deleted_at` where `deleted_at IS NULL`
(`models.Index(fields=["deleted_at"], condition=Q(deleted_at__isnull=True),
name="items_not_deleted_idx")`) — verified to compile to exactly that on
real PostgreSQL (see "Database & migrations"): `CREATE INDEX
items_not_deleted_idx ON public.items USING btree (deleted_at) WHERE
(deleted_at IS NULL)`. Speeds the default manager's `deleted_at IS NULL`
filter on every unscoped lookup without indexing the much rarer
soft-deleted rows. (Django's partial-index `condition=` is Postgres/
sqlite/Oracle-only per Django's own docs; the hermetic sqlite test settings
still create *some* index there, just not a genuinely partial one on
backends that don't support the feature — harmless for this step's
purposes.)

## Conformance (Step 1 vs. Step 2, + fix round)

**Gate-1 decision (recorded in the PR's decision log):** the client-
interchangeability guarantee this Django track works toward is **wire-
contract identity** — byte-identical paths, methods, status codes, and JSON
response bodies to what `backend/fastapi` serves for the same operation —
with best-effort OpenAPI `operationId`/component-name parity, and
Django-only client regeneration documented as an accepted, expected step
(swapping tracks means re-running the client generator against this app's
`/api/schema/` once a later step exposes it, not necessarily getting the
exact committed FastAPI-generated `packages/api-client` as a byte-for-byte
drop-in).

**What Step 1 delivered toward that:** the two contract SOURCES
(`core/contract/errors.py`, `core/contract/pagination.py`) that define the
target shapes, vendored verbatim/near-verbatim, plus the `Item` model — no
DRF view/router/serializer/exception-handler/pagination-class yet.

**What Step 2 (this step, #27) delivers — the DRF contract-EMISSION
layer:** `core/serializers.py` (`ItemOut`/`ItemCreate`/`ItemUpdate` +
health/auth-stub shapes, matched field-for-field to `packages/api-client/
openapi.json`), `core/views.py` (`ItemViewSet` + health/readyz + auth-stub
views, wired via `core/urls.py`/`config/urls.py` reproducing
`backend/fastapi`'s route set — `GET/POST /items`, `GET/PATCH/DELETE
/items/{item_id}`, `/health`, `/readyz`, the `/auth/*` stubs),
`core/exceptions.py` (the custom `EXCEPTION_HANDLER` mapping DRF's own
exception types — and anything unhandled — onto `ErrorEnvelope`, wired via
`REST_FRAMEWORK["EXCEPTION_HANDLER"]`), and `core/pagination.py` (the
custom `PageNumberPagination` subclass emitting `{items, total, page, size,
pages}` instead of DRF's own default `{count, next, previous, results}`
shape, wired via `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]`). The
conformance-proof test suite (`tests/test_conformance_errors.py`,
`tests/test_conformance_pagination.py`) asserts these shapes byte-equal
against `core/contract/`'s vendored Pydantic models for the same inputs —
not just "some 4xx"/"some paginated list".

**Fix round (this state):** an internal review of Step 2 found several real
bugs where this layer broke wire-contract identity rather than merely
diverging from it — see each fix's own commit/docstring for detail:
- A malformed (non-UUID) `item_id` used to raise `django.core.exceptions.
  ValidationError` inside `ItemViewSet.get_object()`'s ORM lookup, which
  escaped the narrower `except (DoesNotExist, ValueError, TypeError)` and
  reached the client as a bare, un-enveloped 500. Fixed: that exception type
  is now caught too (`core/views.py`) — the documented 404 `NotFoundError`
  envelope, verified via a real `GET /items/not-a-uuid` request.
- Every DRF `APIException` subclass without its own explicit branch
  (`AuthenticationFailed`, `ParseError`/malformed JSON, `MethodNotAllowed`,
  `UnsupportedMediaType`, ...) used to fall through `core/exceptions.py`'s
  catch-all straight to a bare 500 with a logged traceback — including for
  ordinary client mistakes, not just genuine bugs. Fixed: a new branch maps
  every remaining `APIException` from its own real `status_code` onto the
  best-fit `ErrorCode`, keeps that real status code (never fakes it to
  500), and only logs at `exception` level for a genuine 5xx — see
  `core/exceptions.py`'s own module docstring for the full mapping table.
  Verified via real requests: malformed JSON → 400 `validation_failed`
  (not 500), `PUT /items/{id}` → 405 `validation_failed` (not 500), bad
  Basic-auth credentials → 401 `unauthenticated` (not 500), a genuine
  `RuntimeError` → still 500 `internal_error` with no `str(exc)` leak.
- DRF's default `DEFAULT_AUTHENTICATION_CLASSES`
  (`SessionAuthentication`+`BasicAuthentication`) was left unset, so every
  view without its own explicit `authentication_classes` override —
  `ItemViewSet` included — silently accepted HTTP Basic credentials against
  Django's `auth_user` table, an auth surface nothing in this block
  populates or intends before Stage 5 (#28). Fixed: `config/settings.py`
  now sets `"DEFAULT_AUTHENTICATION_CLASSES": []` kit-wide; the health/
  readyz/auth-stub views' own explicit `authentication_classes = []`
  (`core/views.py`) is unchanged and now consistent with, rather than the
  only thing closing, that surface.
- `page`/`size` bounds (`page=0`/negative, `size=0`, `size>200`) used to be
  silently accepted or clamped by DRF's own `PageNumberPagination` rather
  than rejected, and a `page` past the last one 404'd ("Invalid page")
  instead of returning an empty page — both real divergences from
  FastAPI's `Depends(PageParams)` behavior. Fixed, turning both into real
  conformance rather than accepted gaps: `core/pagination.py`'s
  `paginate_queryset` now validates `page`/`size` through the SAME
  vendored `PageParams` FastAPI uses (out-of-bounds → 422
  `validation_failed`, verified for `page=0`, `page=-1`, `size=0`,
  `size=201`, `size=500`), and tolerates a past-the-end `page` as `items:
  []` at 200 (verified) rather than DRF's own 404.
- `ModelViewSet` + a router used to also expose `PUT /items/{item_id}`
  (full replace, forced to partial semantics), which `openapi.json` does
  not define at all. Fixed: `ItemViewSet.http_method_names` (`core/
  views.py`) now excludes `"put"` outright, so `PUT` 405s via the
  `APIException` fix above instead of being silently accepted — verified
  a `PUT` now returns 405 and `PATCH` still works.

**Accepted, documented per-framework divergences** (none forced — see each
source's own docstring for the full rationale; the guarantee is
wire-identity on the DOCUMENTED operations and their success/documented-
error responses, not on framework-level plumbing a well-behaved generated
client never triggers):
- `PageParams`'s `extra="forbid"` (an unrecognized query param is a hard
  422 on FastAPI) has no DRF equivalent wired here — an unrelated unknown
  query param is silently ignored (`core/pagination.py`).
- `ItemViewSet.get_object()` treats a malformed (non-UUID) `item_id` path
  segment as 404 (`core/views.py`) where FastAPI's path-typed `item_id:
  uuid.UUID` rejects it at 422 before the handler runs — a routing-level
  type-coercion difference, not a contract-shape one (the underlying 500
  BUG this used to also trigger is the fix above; the 404-vs-422 choice
  itself remains an accepted, deliberate divergence).
- **Framework-level negotiation/parse errors may differ in exact status
  between the two tracks.** A malformed JSON body is DRF's own `ParseError`
  (`status_code = 400`) here vs. FastAPI's 422 for the equivalent case; a
  disallowed method (`PUT`) is 405 on both, but DRF's `UnsupportedMediaType`
  (415) has no FastAPI-side equivalent pinned. None of these are documented
  operations or documented error responses in `packages/api-client/
  openapi.json` — a well-behaved client generated from that frozen schema
  never sends a request that triggers them. The wire-identity guarantee
  this block targets (see "Gate-1 decision" above) covers the DOCUMENTED
  surface; these framework-negotiation edges are honestly out of scope for
  byte-identical status matching, though both sides still return a real,
  enveloped `ErrorEnvelope` (never a bare 500) for every one of them.
- **The 422 `details[]` array's exact content is NOT byte-identical**
  between the two tracks, even though the envelope's outer shape (`code`,
  `status`, `message`) is. `field` differs (DRF's `ValidationError.detail`
  keys are the bare field name, e.g. `"name"`; FastAPI's
  `RequestValidationError.errors()` `loc` includes the request-part prefix,
  e.g. `"body.name"`) and `message` text differs (DRF's own validator
  messages vs. Pydantic's). A client that switches on `error.code` (as
  `core/contract/errors.py`'s own `ErrorBody` docstring already instructs —
  "a client should switch on `code`, never on `message`") is unaffected;
  one that parses `details[].field`/`.message` as a stable, cross-backend
  identifier is not supported by either track's contract.
- **List ordering**: `ItemViewSet.queryset` here is explicitly
  `.order_by("created_at", "id")` (`core/views.py`) — a deterministic,
  repeatable page-to-page order. `backend/fastapi`'s equivalent list query
  currently applies no `ORDER BY` at all. This is flagged, not fixed here
  (out of this fix round's scope, which is this Django block only): the
  FastAPI block should adopt the same deterministic order for genuine
  cross-backend list-order parity — tracked as a follow-up for Step 4 /
  the whole-PR review, not addressed in this commit.

## Security

**Transport security headers (HSTS, `X-Content-Type-Options: nosniff`,
SSL-redirect, `Referrer-Policy`) are deferred, deliberately.** Django's own
`SECURE_HSTS_SECONDS`/`SECURE_CONTENT_TYPE_NOSNIFF`/`SECURE_SSL_REDIRECT`/
`SECURE_REFERRER_POLICY` settings are left unset in `config/settings.py` on
purpose — that job belongs to the same `security-headers` component
backend/fastapi vendors and wires as middleware (Stage 3 Step 3b,
`app/core/security/security_headers/`), and Step 3 of this stage is where
this Django track vendors/wires the equivalent. Setting Django's own
`SECURE_*` values now, ahead of that, would double-stamp the same headers
from two uncoordinated sources once Step 3 lands. **A production
materialization of this block MUST wire that component** (or, until it
exists here, set Django's own `SECURE_*` values itself) — shipping with
neither leaves every response without HSTS/nosniff/frame-options/
referrer-policy protection. See `config/settings.py`'s own comment block
near `REST_FRAMEWORK` for the same note in code.

## Database & migrations

`core/migrations/0001_initial.py` was generated with `manage.py
makemigrations core` against this model and applied with `manage.py
migrate` — **verified against real PostgreSQL 16** (the sandbox's available
cluster; this matrix pins PostgreSQL **18.x** — same documented gap
`backend/fastapi`'s README already carries, not repeated in detail here).
The partial index landed exactly as declared (see "The Item model" and the
transcript in this step's PR description). A create → get round-trip
through `Item.objects` (default manager) and the soft-delete scoping
(`mark_deleted()` + `save()` making a row invisible to `Item.objects` but
still visible via `Item.all_objects`) were both exercised directly against
that real database via `manage.py shell`.

## Testing

`tests/` (pytest + pytest-django + DRF's `APIClient`, all against
`config.settings_test`'s hermetic sqlite — `[tool.pytest.ini_options]` in
`pyproject.toml`):

- `test_items.py` — basic create/list/get/update/soft-delete smoke
  coverage (Step 2's first commit).
- `test_conformance_errors.py` — THE conformance-proof for
  `core/exceptions.py`: triggers a validation failure (422), a missing
  item (404), an unauthenticated/forbidden request (401/403, via a
  throwaway test-only route — see `tests/_conformance_urls.py`), and a
  forced unhandled exception (500); asserts each response body equals the
  `ErrorEnvelope` core/contract/errors.py's own model would produce for
  the same inputs (round-tripped through `ErrorEnvelope.model_validate`
  and, for the 404/500 cases, built directly from `NotFoundError`/
  `AppError`). Also asserts `deleted_at` never appears in any item
  response and `name=""` is rejected at 422. **Fix round additions**
  (every one hits the real route via `APIClient`, not the handler
  function in isolation): `test_malformed_uuid_path_is_404_not_500`,
  `test_malformed_json_body_is_not_500`, `test_put_is_405_not_500`,
  `test_bad_basic_auth_credentials_are_401_not_500` (the last via a new
  throwaway `_BasicAuthOnlyView` in `tests/_conformance_urls.py`, since no
  real route runs `BasicAuthentication` any more after the
  `DEFAULT_AUTHENTICATION_CLASSES = []` fix).
- `test_conformance_pagination.py` — creates N items, asserts `GET /items`
  equals `{items, total, page, size, pages}` cross-checked against
  `core.contract.pagination.Page.create(...)` for the same data. **Fix
  round**: `test_max_page_size_is_capped_at_200` (the old accepted-
  divergence clamp test) is replaced by `test_size_over_200_is_422`
  (same input, now the correct 422 outcome); new
  `test_size_exactly_201_is_422`, `test_size_zero_is_422`,
  `test_page_zero_is_422`, `test_page_negative_is_422`,
  `test_page_past_the_end_is_200_with_empty_items` cover the rest of the
  now-validated `PageParams` bounds.

Verification for this step + fix round: `manage.py check` (hermetic-sqlite),
`manage.py migrate` clean, the full pytest suite green (26 tests — 17 from
Step 2 plus 9 added this fix round: 4 in `test_conformance_errors.py`, 5 net
in `test_conformance_pagination.py`), and `scripts/validate_plugin.py` 0
warnings — see this step's PR description for the full transcript.
Step 1's own real-PostgreSQL-16 verification (model + migration) is
unchanged and not repeated here.

## Judgment calls

- **App label is `core`, not `api`.** The materialized *directory* both
  this block and `backend/fastapi` land in is `apps/api/` (same slot,
  alternative tracks — see this file's top-level description) — but
  Django's own `INSTALLED_APPS` app-label convention is a different
  namespace from that directory name, and naming the Django app itself
  `api` would read as "the whole API" when it's actually just the model +
  contract package this step ships. `core` avoids that collision and
  leaves room for a later `api` app (views/serializers/routers) if Step 2+
  wants that split instead of extending this one.
- **No admin/sessions/messages/staticfiles apps.** This is an API-only
  block (JSON over DRF, no server-rendered templates) as of this step — the
  Django defaults that assume a browsable admin site or session-backed
  auth aren't needed yet and add attack surface/migration weight for
  nothing consumed. Add them back deliberately if a materialized project's
  Step 2+ needs the admin site.
- **`psycopg[binary]`, not bare `psycopg` + system libpq.** The `[binary]`
  extra vendors a self-contained C extension wheel with no local libpq
  headers/toolchain required for `uv sync` to succeed — matches this kit's
  "no surprise system deps" posture elsewhere (e.g. `asyncpg` needing no
  separate system package). A project deploying with its own optimized
  libpq build can swap to bare `psycopg` + `psycopg[c]` later; not this
  block's default.
- **`SECRET_KEY` has no fallback value, not even in `DEBUG` mode.** Unlike
  Django's own `startproject` scaffold (which ships a real, checked-in
  dev key), this block's instructions are explicit: "SECRET_KEY from env —
  NEVER hardcode." A missing value fails immediately and loudly at
  settings-module import (mirroring `backend/fastapi`'s "no default means
  required" `AppSettings` convention) rather than silently running on a
  fabricated key that risks surviving into a real deployment.
  `config/settings_test.py` sets an explicit, clearly-named placeholder
  value only for the hermetic-sqlite path, and only via `setdefault` (a
  real `SECRET_KEY` in the environment still wins).
- **PostgreSQL 16, not the matrix's pinned 18.x, for the real-DB
  verification.** Same gap `backend/fastapi`'s README already documents —
  the sandbox only had a startable 16 cluster; nothing in this block's
  model or migration is 18-specific, but this is a noted gap, not a
  substitute for an eventual 18 run.
- **`gunicorn` pinned to `26.0.*`, not `23.0.*`.** This step's own
  instructions suggested "gunicorn or uvicorn for asgi" as an illustrative
  example version; PyPI's actual current stable at verification time was
  `26.0.0` (verified via `pip index versions gunicorn`) — pinned the real
  current line rather than the illustrative one, per this catalog's
  "recall is not a source, verify against the registry" convention (see
  compatibility-matrix.md's "Version check").
- **`ItemManager`/`ItemQuerySet` scope every default lookup, `Item.
  all_objects` stays unscoped.** Django's own docs on custom managers
  recommend keeping an unscoped default manager available even when a
  project narrows `objects` — some internal machinery expects one to
  exist. `all_objects` is that escape hatch, doubling as the "hard-delete
  cleanup job" / "admin view that needs soft-deleted rows" access path
  `ItemQuerySet.with_deleted()` also provides via the scoped manager.
