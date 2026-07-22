<!-- fragment: block:components/security/idempotency -->

## Setup
Copy the `idempotency/` directory into
`app/core/security/idempotency/`. FastAPI: `add_idempotency(app,
store=InMemoryIdempotencyStore())` once at app construction — the
middleware is a no-op for any request without an `Idempotency-Key` header,
so wiring it whole-app is safe even if only some routes send the header.
Django: add
`"app.core.security.idempotency.django.IdempotencyMiddleware"` to
`MIDDLEWARE`, and optionally set `IDEMPOTENCY_HEADER_NAME` in
`settings.py` (default `"HTTP_IDEMPOTENCY_KEY"`).

## Maintenance
`InMemoryIdempotencyStore` is per-process and does not reserve across the
request lifecycle — re-evaluate against the Stage 11 Redis-backed store
once a deployment moves to multiple workers/replicas, or once true
concurrent (not just retried) double-submission needs to be closed with
atomic `SET NX` reservation.
