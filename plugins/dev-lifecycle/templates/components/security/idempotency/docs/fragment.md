<!-- fragment: block:components/security/idempotency -->

## Setup
Copy the `idempotency/` directory into
`app/core/security/idempotency/`. **This middleware requires a
`principal_getter` and MUST be wired AFTER authentication** — see the
component README's "Principal scoping" section before wiring this up; a
default-DENY anonymous policy applies to any request `principal_getter`
can't identify. FastAPI: `add_idempotency(app,
store=InMemoryIdempotencyStore(), principal_getter=lambda request:
request.state.user_id)`, registered BEFORE any auth middleware (so auth
runs first on the request path) — the middleware is a no-op for any
request without an `Idempotency-Key` header, so wiring it whole-app is
safe even if only some routes send the header. Django: add
`"app.core.security.idempotency.django.IdempotencyMiddleware"` to
`MIDDLEWARE` AFTER `AuthenticationMiddleware`, set
`IDEMPOTENCY_PRINCIPAL_GETTER` to a dotted path (e.g. this module's own
`default_principal_getter`), and optionally set `IDEMPOTENCY_HEADER_NAME`
in `settings.py` (default `"HTTP_IDEMPOTENCY_KEY"`).

## Maintenance
`InMemoryIdempotencyStore` is per-process and does not reserve across the
request lifecycle — re-evaluate against the Stage 11 Redis-backed store
once a deployment moves to multiple workers/replicas, or once true
concurrent (not just retried) double-submission needs to be closed with
atomic `SET NX` reservation. It now also bounds itself with a
`ttl_seconds` idle-expiry (default 24h) and an optional `max_keys` cap —
tune `ttl_seconds` down if the deployment's realistic retry window is much
shorter than 24h.
