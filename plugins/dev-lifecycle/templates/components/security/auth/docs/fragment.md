<!-- fragment: block:components/security/auth -->

## Setup
Copy the `auth/` directory into `app/core/security/auth/`. This ships
`_core.py` only — a framework-neutral `PasswordService` (Argon2id) +
`TokenService` (PyJWT HS256 access/refresh) + `AuthService` orchestrator.
Wiring it into a live backend (a FastAPI/Django adapter implementing
`UserStore`/`RefreshTokenStore` against a real ORM, constructing
`AuthService` with a real signing key from `secrets-loading/` and real
TTLs at app startup, and mapping its exceptions onto `error-envelope/`'s
`ErrorCode` — `InvalidCredentials`/`InvalidToken`/`TokenReused` →
`unauthenticated`/401, `EmailAlreadyExists` → `conflict`/409) is separate
work, not part of this drop-in. Add `pyjwt==2.13.*` and
`argon2-cffi==25.1.*` to the backend's `pyproject.toml` and to
`references/compatibility-matrix.md`'s Backend — Python row when that
wiring lands. Never hardcode the JWT signing key — resolve it through
`secrets-loading/`, and rotate it per environment.

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
