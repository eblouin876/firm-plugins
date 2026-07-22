<!--
block: components/security/rate-limiting  # catalog component
last-verified: 2026-07-22
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
needs:
  - starlette/fastapi (via the project's FastAPI install): the dependency + middleware variants in fastapi.py
  - django (5.2.x): the middleware variant in django.py
  - a shared store for multi-process/multi-replica deployments (optional, Stage 11): InMemoryBucketStore is per-process only -- see Judgment calls
exposes:
  - BucketStore (Protocol), InMemoryBucketStore, RateLimitResult, check(store, key, *, capacity, refill_per_second, now=None), client_ip_key(remote_addr, forwarded_for, *, trusted_hops=0), validate_refill_rate(refill_per_second) -- in _core.py
  - fastapi.py: make_rate_limit_dependency(store, *, capacity, refill_per_second, key_func=None, trusted_hops=0), RateLimitMiddleware
  - django.py: RateLimitMiddleware (settings-configurable: RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_SECOND, RATE_LIMIT_TRUSTED_HOPS)
  - its co-located doc fragment: docs/fragment.md
-->

# rate-limiting

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: a stdlib token-bucket limiter with
pluggable storage in `_core.py`, a FastAPI dependency + middleware pair in
`fastapi.py`, and a Django `MIDDLEWARE` class in `django.py` — both
returning `429` with a `Retry-After` header on deny. Embodies
`references/security/secure-baseline.md`'s "Rate limiting & lockout"
section. Lives at `templates/components/security/rate-limiting/` in this
repo; Stage 3-4 backend blocks copy the whole directory into
`app/core/security/rate_limiting/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- The token bucket
- Storage: pluggable, Redis stubbed for Stage 11; bounded by idle-TTL/cap
- The default key function: rightmost-minus-trusted-hops
- FastAPI: dependency vs. middleware
- Django: settings-configurable
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Starlette/FastAPI** (via the project's FastAPI install) — the
  dependency and middleware variants in `fastapi.py`.
- **Django 5.2.x** — the `MIDDLEWARE` class in `django.py`.
- **A shared store for multi-process/multi-replica deployments (optional,
  Stage 11)** — `InMemoryBucketStore` is per-process; see "Judgment calls".

**EXPOSES**
- `BucketStore` (a `Protocol` — the storage seam), `InMemoryBucketStore`
  (the stdlib implementation, with `ttl_seconds`/`max_keys` bounds),
  `RateLimitResult` (`allowed`, `remaining`, `retry_after`), `check(store,
  key, *, capacity, refill_per_second, now=None)` (the convenience wrapper
  both adapters call), `client_ip_key(remote_addr, forwarded_for, *,
  trusted_hops=0)` (the default key function's logic),
  `validate_refill_rate(refill_per_second)` (construction-time guard
  against `refill_per_second<=0`) — all in `_core.py`.
- `fastapi.py`: `make_rate_limit_dependency(store, *, capacity,
  refill_per_second, key_func=None, trusted_hops=0)` (per-route),
  `RateLimitMiddleware` (whole-app).
- `django.py`: `RateLimitMiddleware`, configurable via `RATE_LIMIT_CAPACITY`
  / `RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUSTED_HOPS` settings or
  direct constructor kwargs.
- Its co-located doc fragment: `docs/fragment.md`.

## The token bucket

Classic token bucket: a key's bucket starts full (`capacity` tokens),
refills continuously at `refill_per_second`, and each allowed request
consumes one token. Refill is computed **lazily at access time** (elapsed
time since the bucket's last touch × `refill_per_second`), not via a
background timer/thread — no scheduler, no idle CPU cost, and the math is
exactly reproducible given an injected `now` (which is exactly how
`tests/test_core.py` gets deterministic refill assertions without sleeping
in a test).

## Storage: pluggable, Redis stubbed for Stage 11; bounded by idle-TTL/cap

`BucketStore` is a `Protocol` — `take(key, *, capacity, refill_per_second,
now) -> RateLimitResult`. `InMemoryBucketStore` is the stdlib
implementation this component ships (a `dict` + a `threading.Lock` for
atomicity within one process). **This module does not import `redis`** — a
Stage 11 Redis-backed `BucketStore` (atomic across multiple app processes
via a Lua script, unlike a Python-level lock) plugs into the exact same
Protocol without either framework adapter changing; that's the whole point
of the seam being a `Protocol` rather than `InMemoryBucketStore` being
hard-wired into `fastapi.py`/`django.py`.

`InMemoryBucketStore(ttl_seconds=900.0, max_keys=None)` bounds itself: every
`take()` sweeps buckets idle beyond `ttl_seconds` (default 15 minutes — a
bucket idle that long has fully refilled to `capacity` anyway, so evicting
it changes nothing observable), and an optional `max_keys` cap evicts the
single oldest-by-last-touch bucket whenever a `take()` would exceed it.
Without this, a high-cardinality key space (e.g. per-IP keys under churn
from many distinct clients) would grow the store's `dict` without bound.

## The default key function: rightmost-minus-trusted-hops

**Corrected posture (previously stated backwards):** an edge proxy (ALB,
CloudFront, a correctly configured nginx/Caddy) **APPENDS** its observed
peer address to `X-Forwarded-For` when forwarding a request — it does
**NOT** strip or overwrite whatever the client already put there. A client
fully controls the header's contents; only entries appended by a proxy
this project actually controls are trustworthy, and those are always the
RIGHTMOST entries, never the leftmost.

`client_ip_key(remote_addr, forwarded_for, *, trusted_hops=0)`:
- `trusted_hops=0` (the default) — ignore `X-Forwarded-For` entirely, use
  `remote_addr` (the actual TCP peer). Safe everywhere, including with no
  proxy at all or an unconfirmed proxy config.
- `trusted_hops=N` (`N >= 1`) — take the Nth-from-right entry: the address
  the OUTERMOST of the N trusted proxies in front of this app saw when it
  received the request. **ALB example:** a single ALB directly in front of
  the app, nothing else — `trusted_hops=1` reads the rightmost entry, the
  address ALB itself observed. A project MUST set `trusted_hops` to the
  exact number of trusted proxies it controls, deliberately, per
  environment — never guessed, and never higher than the real proxy count
  (that would trust an entry the client could have supplied itself). If
  the header has fewer entries than `trusted_hops`, this falls back to
  `remote_addr` rather than guessing.

Both framework adapters thread `trusted_hops` straight through to this
function — set it deliberately, per environment, never as a blanket
default.

## FastAPI: dependency vs. middleware

`RateLimitMiddleware` rate-limits every request (the general per-IP API
ceiling secure-baseline calls for). `make_rate_limit_dependency(...)`
layers a stricter, route-specific limit on top (e.g. 5/minute on `/login`
regardless of the general middleware's looser whole-app ceiling) — both can
run together, against different `BucketStore` instances or the same one
with a different key, since they're independent by construction.

## Django: settings-configurable

Django instantiates a `MIDDLEWARE` entry with only `get_response` — there's
no way to pass constructor kwargs from `settings.MIDDLEWARE` itself — so
`RateLimitMiddleware` reads `RATE_LIMIT_CAPACITY` /
`RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUSTED_HOPS` from
`django.conf.settings` by default, falling back to `capacity=60`,
`refill_per_second=1.0`, `trusted_hops=0` if unset. Explicit constructor
kwargs (used throughout this component's own tests) override the
settings-derived value when passed, for a project wiring the middleware by
hand. `refill_per_second` is validated (`validate_refill_rate`) at
construction time regardless of where it came from.

## Testing

`tests/test_core.py` covers the refill math with explicit deterministic
`now` values (first request allowed, burst-to-capacity then denied, exact
one-token-per-second refill, retry-after shrinking as elapsed time grows,
the bucket never exceeding `capacity`), per-key isolation, every branch of
`client_ip_key`'s corrected trust posture (XFF ignored by default,
rightmost-entry selection when trusted, a spoofed LEFTMOST entry NOT
changing the selected key with `trusted_hops=1`, multi-hop selection,
falling back to `remote_addr` on an absent/blank/insufficient XFF),
`validate_refill_rate`'s rejection of zero/negative rates, and
`InMemoryBucketStore`'s idle-TTL eviction and `max_keys` cap.
`tests/test_fastapi.py` exercises both the middleware and dependency
variants against a real FastAPI `TestClient` (allow-then-429,
`Retry-After` present, an undecorated route unaffected by a decorated
one's drained bucket, and construction-time rejection of
`refill_per_second<=0` for both variants). `tests/test_django.py`
exercises the middleware via `RequestFactory` the same way, plus the
XFF-ignored-by-default vs. rightmost-entry-honored-when-`trusted_hops=1`
behavior (including that a spoofed leftmost entry does not bypass the
limit) against `REMOTE_ADDR`/`HTTP_X_FORWARDED_FOR`, and the same
construction-time `refill_per_second<=0` rejection.

Run:
```
uv run --python 3.13 --with fastapi --with httpx --with pytest --with 'django==5.2.*' -- \
  pytest templates/components/security/rate-limiting/tests/ -q
```

## Judgment calls

- **`InMemoryBucketStore` is per-process, documented rather than hidden.**
  A multi-worker/multi-replica deployment gives each process its own
  independent bucket for the same key, so the *effective* limit becomes
  roughly N× the configured rate, not a hard shared ceiling. This is stated
  plainly in the store's own docstring and in the component README rather
  than presented as a drop-in "just works" solution — a project that needs
  a true shared ceiling across processes needs the Stage 11 Redis-backed
  store, not this one. Shipping the in-memory store anyway (rather than
  shipping nothing until Stage 11) was judged the right call: a
  single-process dev server and a single-replica deployment both get a
  fully correct limiter today, and the seam (`BucketStore` Protocol) is
  already in place for the upgrade.
- **`refill_per_second` as a float, not "N requests per window".** A
  window-based limiter ("100 requests per minute") has a well-known
  boundary problem (a burst just before and just after a window edge can
  total nearly 2×the nominal limit); token bucket with continuous refill
  doesn't have that edge. A caller wanting "N per minute" computes
  `refill_per_second=N/60` — a one-line conversion documented in the
  dependency's own docstring example, not worth a second config shape.
- **`client_ip_key` defaults to distrusting `X-Forwarded-For`.** The unsafe
  default here would be trusting it — a spoofable header trusted by
  default turns the whole rate limiter into "attacker picks their own
  bucket key," a total bypass. Requiring an explicit `trusted_hops>=1`
  opt-in, with the risk spelled out in the docstring right next to the
  parameter, matches secure-baseline's "deny by default, explicit opt-out"
  posture applied to a trust decision instead of an access decision.
- **`trusted_hops: int`, not `trust_proxy: bool`.** A boolean flag can only
  express "trust the whole header" or "trust nothing" — it can't express
  "trust exactly the entries my own N proxies appended," which is the only
  thing that's actually safe to trust. An integer hop count is both more
  correct (it matches how XFF is actually built, hop by hop) and
  self-documenting at the call site (`trusted_hops=1` reads as "one proxy
  in front of this app," not an opaque `True`).
- **Insufficient `X-Forwarded-For` entries fall back to `remote_addr`,
  not to whatever's leftmost.** If `trusted_hops=2` but the header only has
  one entry, something is wrong (a misconfigured proxy chain, or a
  malformed/attacker-supplied header) — silently taking whatever's there
  would be guessing. Falling back to the real peer address is the same
  "can't verify, use the safe default" posture the whole default-`trust`
  design already takes.
- **`InMemoryBucketStore`'s idle-TTL default (15 min) is chosen for "no
  observable behavior change," not an arbitrary round number.** A bucket
  idle for 15 minutes has necessarily refilled to full `capacity` (for any
  `refill_per_second` a sane rate limit would use) — evicting it and
  starting fresh on the next `take()` produces IDENTICAL behavior to
  keeping it around, so the TTL closes the unbounded-memory-growth risk
  with zero functional downside for a legitimately-behaving client.
- **`refill_per_second<=0` rejected at construction, not handled at
  `check()`-time with a capped `retry_after`.** A limiter that never
  refills isn't a token bucket — it's a different feature (a fixed,
  one-time quota) wearing this component's API. Rejecting it loudly at
  construction surfaces a misconfiguration immediately, at startup/wiring
  time, rather than lying dormant until the bucket first empties and a
  real caller's 429 response crashes into a 500.
