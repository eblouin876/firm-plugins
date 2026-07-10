<!--
library: fastapi
versions-covered: "0.11x–0.13x, Pydantic v2"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://fastapi.tiangolo.com
-->

# FastAPI / API layer conventions

Granular guidance for the API layer. Read after detecting FastAPI. Subordinate to the project's existing conventions — when they conflict, the project wins.

## Contents
- Version check (do this first)
- Project structure
- Schemas (Pydantic)
- Routes & dependency injection
- Validation & error handling
- Authentication & authorization
- Async discipline
- Background work
- Pagination, filtering, versioning
- Docs & testing

## Version check (do this first)
Confirm the **FastAPI version** (still 0.x with monthly minors — pin it in the lockfile) and, decisively, the **Pydantic major** the project is on. Pydantic v1 and v2 are effectively different libraries and change how schemas, validators, and settings are written — that check and its idioms live in `pydantic.md`; **load it whenever you touch request/response models.** If unsure whether a FastAPI API exists in the installed version, check the current docs/release notes rather than recalling.

## Project structure
Favor a layered layout and mirror whatever the project already uses:
- `app/main.py` — app factory, middleware, router registration, lifespan.
- `app/routers/` (or `api/`) — route definitions grouped by resource, included via `APIRouter`.
- `app/schemas/` — Pydantic request/response models.
- `app/models/` — SQLAlchemy ORM models (see `database.md`).
- `app/services/` or `app/crud/` — business logic / persistence operations.
- `app/deps.py` — shared dependencies (DB session, current user, pagination).
- `app/core/` — config/settings, security, constants.

Keep route functions thin: validate, delegate to a service, return a response model.

## Schemas (Pydantic)
> Pydantic depth (v1↔v2 idioms, validators, settings) is in `pydantic.md` — load it for schema work. The FastAPI-integration essentials:
- Separate schemas from ORM models — never reuse a SQLAlchemy model as a request/response body.
- Use the base/create/update/read split: a base with shared fields, a `Create` schema (accepts inputs like a raw password), an `Update` schema (fields optional), and a `Read`/`Out` schema that **never** exposes secrets (hashed passwords, internal flags, tokens).
- Set `response_model` on routes so responses are filtered to the declared schema — this prevents accidental data leaks.
- Constrain at the field level (`Field(..., min_length=, max_length=, ge=, le=, pattern=)`, `EmailStr`, etc.); field constraints become automatic 422 responses with precise errors — no manual validation code.

## Routes & dependency injection
- Group routes with `APIRouter`, prefix and tag them, and include them in the app.
- Use FastAPI's dependency injection for cross-cutting concerns: DB session, authenticated user, pagination params, settings. Don't reach for globals.
- Declare explicit status codes (`status_code=status.HTTP_201_CREATED` on creates, 204 on deletes with no body, etc.).
- Use path/query/body parameter typing fully so OpenAPI and validation are accurate.

## Validation & error handling
- Let schema validation reject malformed input automatically (422). Don't hand-roll what a field constraint expresses.
- Raise `HTTPException` with the correct status and a clear, non-sensitive `detail` for expected error conditions (404 not found, 403 forbidden, 409 conflict).
- Add exception handlers for domain exceptions so services can raise meaningful errors that map to HTTP responses centrally.
- Never leak stack traces, SQL, or internal identifiers to clients. Log the detail server-side; return a safe message.

## Authentication & authorization
- Authentication: verify identity (e.g. OAuth2 password/bearer with JWT, or whatever the project uses). Hash passwords with a strong adaptive algorithm (bcrypt/argon2 via passlib or equivalent) — never store or log plaintext.
- Authorization: check permissions on every protected route, enforced via a dependency (e.g. `current_user` / role/scope checks). Authentication ≠ authorization — confirm the user is allowed to act on *this* resource, not merely logged in.
- Keep secrets (JWT signing keys, DB creds) in config/env via `pydantic-settings`; never hardcode, never commit, never log.
- Set sensible token expiry and validate tokens fully (signature, expiry, audience/issuer where relevant).

## Async discipline
- If the app is async, keep the whole request path async: `async def` endpoints, async DB session, async drivers (`asyncpg`). Don't call blocking I/O inside async routes — it stalls the event loop.
- Offload unavoidable blocking/CPU-bound work to a threadpool (`run_in_threadpool` / `anyio.to_thread`) or a task queue.
- If the app is sync, stay sync consistently. Don't mix paradigms within a request path.

## Background work
- Use `BackgroundTasks` for light, fire-and-forget work tied to a request (sending an email after a response).
- For heavier, retryable, or scheduled work, use the project's task queue (Celery/arq/taskiq). Don't block the request to do long work inline.

## Pagination, filtering, versioning
- Paginate list endpoints (limit/offset or cursor); don't return unbounded collections.
- Make filtering/sorting explicit and validated via query-param schemas.
- Version the API when you have external consumers (path prefix like `/v1` or header-based), so changes don't break clients.

## Docs & testing
- The OpenAPI docs are generated from your types and schemas — keep them accurate by typing fully and using `response_model`, tags, and summaries/descriptions.
- Test with `pytest` and FastAPI's `TestClient` / `httpx.AsyncClient`. Cover success, validation failure (422), auth failure (401/403), not-found (404), and key business edge cases. Use a separate test database/transaction rollback per test.
