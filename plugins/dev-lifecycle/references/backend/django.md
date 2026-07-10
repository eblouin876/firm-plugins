<!--
library: django
versions-covered: "5.2 LTS, 6.0"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://docs.djangoproject.com
  - https://www.djangoproject.com/download/
-->

# Django conventions

Granular guidance for Django apps — the server-rendered + HTMX path in this firm (pairs with `htmx.md` for the frontend enhancement). Read after detecting Django (`manage.py`, `django` in the manifest, `settings.py`). Subordinate to the project's existing conventions.

## Version check (do this first)
Django does time-based releases (~every 8 months); the `x.2` release of each series is the LTS.

- **Current: Django 6.0** (latest feature release) — requires **Python 3.12+**. Use it for a greenfield project that will track releases.
- **Django 5.2 (LTS)** — supported through April 2028; the right anchor for a project that wants a long support window.
- **Django 4.2 LTS reached EOL in April 2026** and **5.1 in December 2025** — do not start new projects on them, and treat existing ones as upgrade-urgent (no more security patches).

Match the installed version's idioms; confirm from the manifest/lockfile. `python -c "import django; print(django.get_version())"` on an existing project.

## Project layout
- Standard Django project + apps structure; one app per bounded domain. Keep apps focused and cohesive.
- Settings split by environment (base + dev/prod), config from env vars (12-factor); secrets never committed. Use `pathlib.Path` for path settings.

## Models & ORM
- Models are the schema source of truth; make constraints explicit (`null`/`blank` intentionally distinct, `unique`, `UniqueConstraint`/`CheckConstraint` in `Meta.constraints`, indexes in `Meta.indexes`).
- Use `db_default` for database-level defaults and `GeneratedField` for computed columns where they fit (5.0+).
- **Avoid N+1**: use `select_related` (FK/one-to-one joins) and `prefetch_related` (many relations). Push work into the query (`annotate`, `aggregate`, `F`/`Q` expressions), not Python loops.
- Every schema change is a migration (`makemigrations` → **review** → `migrate`); never edit an applied migration in shared environments. Sequence destructive changes expand → backfill → contract.

## Views, forms & HTMX
- Prefer the thinnest view that does the job; keep business logic in services/model methods, not fat views.
- Forms (or ModelForms) own validation — the server is the source of truth. Re-render the form partial with inline errors on failure.
- For HTMX: detect `HX-Request` and return the **partial template** (a fragment) instead of the full page; drive client behavior with response headers (`HX-Redirect`, `HX-Trigger`). Test partials as backend view tests (see `backend-testing.md`). Full HTMX conventions are in `htmx.md`.
- Use the template engine for rendering only — compute in the view; no business logic in templates.

## Security (Django gives you a lot — don't disable it)
- Keep the built-in protections on: CSRF middleware, the ORM's parameterized queries (never `.raw()`/`.extra()` with interpolated input), template auto-escaping (don't blanket-`|safe`), and `SECURE_*` settings in prod (HTTPS redirect, HSTS, secure cookies).
- `DEBUG = False` in production; set `ALLOWED_HOSTS`. Authn via the auth framework; authorization checked per view (permissions/`LoginRequiredMixin`), not just "is logged in."
- Passwords via Django's hashers (Argon2/bcrypt available as extras) — never plaintext.

## Async
- Django supports async views and an async-capable ORM; use it where it helps (I/O-bound views), but don't mix sync ORM calls into an async path. Match the project's existing sync/async choice rather than introducing async piecemeal.

## Testing
- `pytest-django` (or Django's `TestCase`) with per-test transaction rollback; the test client for views, the ORM for setup. Test views, forms, and HTMX partial responses (right fragment + status). See `backend-testing.md`.
