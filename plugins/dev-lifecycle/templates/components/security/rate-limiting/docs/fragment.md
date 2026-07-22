<!-- fragment: block:components/security/rate-limiting -->

## Setup
Copy the `rate-limiting/` directory into
`app/core/security/rate_limiting/`. FastAPI: `app.add_middleware(
RateLimitMiddleware, store=..., capacity=..., refill_per_second=...)` for a
general per-IP ceiling, and `make_rate_limit_dependency(...)` on top of any
auth/expensive endpoint that needs a stricter limit. Django: add
`"app.core.security.rate_limiting.django.RateLimitMiddleware"` to
`MIDDLEWARE` and set `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_PER_SECOND`
in `settings.py`. Only set `trust_proxy=True` (or `RATE_LIMIT_TRUST_PROXY`)
after confirming the deployment's edge strips/overwrites client-supplied
`X-Forwarded-For`.

## Maintenance
`InMemoryBucketStore` is per-process — re-evaluate against the Stage 11
Redis-backed store once a deployment moves to multiple workers/replicas and
the effective limit (roughly N× the configured rate) stops being
acceptable.
