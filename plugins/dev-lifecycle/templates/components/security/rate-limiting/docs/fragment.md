<!-- fragment: block:components/security/rate-limiting -->

## Setup
Copy the `rate-limiting/` directory into
`app/core/security/rate_limiting/`. FastAPI: `app.add_middleware(
RateLimitMiddleware, store=..., capacity=..., refill_per_second=...)` for a
general per-IP ceiling, and `make_rate_limit_dependency(...)` on top of any
auth/expensive endpoint that needs a stricter limit. Django: add
`"app.core.security.rate_limiting.django.RateLimitMiddleware"` to
`MIDDLEWARE` and set `RATE_LIMIT_CAPACITY` / `RATE_LIMIT_REFILL_PER_SECOND`
in `settings.py`. Only set `trusted_hops` (or `RATE_LIMIT_TRUSTED_HOPS`) to
the EXACT number of trusted proxies in front of this app, once confirmed —
e.g. a single ALB directly in front is `trusted_hops=1`. Remember: edge
proxies APPEND to `X-Forwarded-For`, they do not strip the client's own
entries — `trusted_hops` reads from the RIGHT end of the header, never the
leftmost entry.

## Maintenance
`InMemoryBucketStore` is per-process — re-evaluate against the Stage 11
Redis-backed store once a deployment moves to multiple workers/replicas and
the effective limit (roughly N× the configured rate) stops being
acceptable. It's now also bounded by an idle-TTL (default 15 min) and an
optional `max_keys` cap — tune `ttl_seconds` down if a much shorter idle
window is more appropriate for a given key space's cardinality.
