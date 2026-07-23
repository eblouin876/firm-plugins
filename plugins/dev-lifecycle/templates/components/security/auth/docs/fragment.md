<!-- fragment: block:components/security/auth -->

## Setup
Copy the `auth/` directory into `app/core/security/auth/` (or, on the
Django track, `core/security/auth/`). Ships `_core.py` — a
framework-neutral `PasswordService` (Argon2id) + `TokenService` (PyJWT
HS256 access/refresh) + `AuthService` orchestrator — `fastapi.py` — the
`HTTPBearer` scheme, `build_get_current_principal` (a dependency factory
resolving a bearer token to `AccessClaims`), `require_roles` (role-gated
dependency factory), and `AUTH_ERROR_HTTP` (exception type -> `(status,
ErrorCode string)` table) — and `django.py` — the Django/DRF equivalent:
`resolve_principal(request, auth_service)` and `require_roles(request,
auth_service, *roles)` (both plain awaited helpers, since Django/DRF has
no `Depends()`-style auto-invoked injection point to compose against),
`InsufficientRole`, and the identically-shaped `AUTH_ERROR_HTTP`. Copy
only the adapter file(s) your track actually uses (a FastAPI project never
vendors `django.py`, and vice versa) alongside `_core.py`. Add an
`__init__.py` re-exporting the vendored files' public surface — see
backend/fastapi's `app/core/security/auth/__init__.py` (FastAPI track) or
backend/django's `core/security/auth/__init__.py` (Django track) for the
exact shape.

Vendoring `_core.py`+the framework adapter is NOT the whole wiring job — a
project still needs, as its OWN (non-vendored) app code: `UserStore`/
`RefreshTokenStore` implementations against a real ORM/DB (these import
the app's models, so they can never be part of this vendored, framework-
neutral component); `AuthService` construction with a real signing key
(via `secrets-loading/`, never hardcoded — rotate per environment) and
real TTLs at app startup; real route handlers calling `AuthService`'s
register/login/refresh/logout/resolve_access; and an app-level exception
handler registered for the `AuthError` base class that renders
`AUTH_ERROR_HTTP`'s mapping as the app's own `ErrorEnvelope` (catches
every subclass via one registration — Starlette-family frameworks walk an
exception's MRO against registered handlers; a DRF `EXCEPTION_HANDLER`
does the equivalent `isinstance` walk by hand). `pyjwt==2.13.*` and
`argon2-cffi==25.1.*` are already in `references/compatibility-matrix.md`'s
Backend — Python row; add the matching pins to the consuming backend's own
`pyproject.toml`/`requirements`.

**Reference implementations:** `backend/fastapi` (Stage 5a, #41) was the
first block to complete this wiring end to end — see that block's
README.md "Auth" section and `app/core/security/auth/stores.py` for a
concrete `UserStore`/`RefreshTokenStore` implementation, and `app/main.py`'s
`_auth_error_handler` for the exception-handler side. `backend/django`
(Stage 5b, #44) is the Django-track reference — see that block's
`core/security/auth/stores.py` for its Django-async-ORM `UserStore`/
`RefreshTokenStore` implementation and `core/exceptions.py` for the
DRF-side exception mapping.

## Maintenance
`AuthService.refresh`'s reuse-detection state machine is the security-
critical core of this component — re-run `tests/test_core.py` after any
change to `_core.py`, especially the "reuse revokes the whole family"
test, before shipping. `PasswordService.needs_rehash()` exists so a
project can tighten Argon2id's cost parameters over time and transparently
upgrade old hashes on next successful login, rather than a bulk
migration — wire that check into the framework adapter's login flow once
it exists. Re-verify the PyJWT/argon2-cffi pins against
`references/compatibility-matrix.md` on the same cadence as the rest of
the Backend — Python row.
