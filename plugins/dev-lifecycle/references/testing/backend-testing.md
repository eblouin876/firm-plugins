<!--
library: pytest
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Backend testing conventions (pytest)

Guidance for testing FastAPI/Django + SQLAlchemy code with pytest. Read after detecting a Python backend. The project's existing conventions override anything here.

## Contents
- Structure & fixtures
- Test data
- Database isolation
- Testing FastAPI endpoints (sync & async)
- Testing Django
- Mocking boundaries
- What to test at each level

## Structure & fixtures
- Mirror the project's layout (`tests/` mirroring the package, or as configured). Name tests `test_*`; name functions so failures read as sentences.
- Use `pytest` fixtures for setup/teardown and shared resources (DB session, test client, authenticated user). Scope them deliberately (`function` for isolation, `session` for expensive immutable setup).
- Put broadly shared fixtures in `conftest.py` at the right level; keep test-specific setup near the test.
- Use `@pytest.mark.parametrize` to cover many input/output cases without duplication.

## Test data
- Build entities with factories (e.g. `factory_boy`) or small helper builders, not hand-assembled dicts copied across tests. Factories make intent clear and reduce breakage when models change.
- Each test creates the data it needs; don't depend on data left by another test or on a shared seeded fixture you can't see.

## Database isolation
- Tests hit a **real database** (a test Postgres, ideally matching prod — not SQLite-as-a-shortcut if the app uses Postgres features), or are structured so DB-dependent logic is integration-tested against the real engine.
- **Isolate every test:** wrap each in a transaction rolled back at teardown, or recreate/truncate schema per test. No test should see another's writes.
- Run migrations (or create the schema from models) to build the test DB so it matches what ships.
- Keep the unit layer DB-free where logic allows; reserve DB hits for integration tests.

## Testing FastAPI endpoints (sync & async)
- Use FastAPI's `TestClient` (sync) or `httpx.AsyncClient` with an ASGI transport (async) — match the app's paradigm; for an async app, test async with `pytest-asyncio`.
- Override dependencies (`app.dependency_overrides`) to inject the test DB session and a test user instead of the real ones.
- Assert on status code *and* response body shape/values. Cover: success, validation failure (422), auth failure (401/403), not-found (404), and conflict (409) where relevant.
- Test that protected routes actually enforce authz — a test that hits an endpoint as the wrong user and expects a 403 is high-value (guards against the OWASP A01 issues code-review looks for).

## Testing Django
- Use `pytest-django` (or Django's `TestCase`) with the project's conventions. Use the test client for views, and the ORM for setup.
- Let the framework manage the test database and per-test transaction rollback.
- Test views, forms, and any HTMX partial responses (assert the right fragment/template and status are returned).

## Mocking boundaries
- **Mock at the edge:** external HTTP APIs, third-party SDKs, email/SMS senders, payment providers, the clock, and randomness. Don't mock your own service/CRUD layer in an integration test — then you're testing mocks, not code.
- Freeze time (`freezegun` or injectable clock) for time-dependent logic so tests are deterministic.
- Prefer faking a boundary with a controllable test double over patching deep internals; patching internals couples tests to implementation.

## What to test at each level
- **Unit:** pure functions, validation logic, business rules, schema behavior — fast, no DB, no network.
- **Integration:** an endpoint through to the database; a service that coordinates several pieces; a migration's effect. Real DB, mocked external edges.
- **Don't** write an e2e/HTTP test for something a unit test covers more precisely — push tests down the pyramid where you can.
