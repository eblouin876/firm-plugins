<!--
block: components/security/rate-limiting  # catalog component
needs:
  - starlette/fastapi (via the project's FastAPI install): the dependency + middleware variants in fastapi.py
  - django (5.2.x): the middleware variant in django.py
  - a shared store for multi-process/multi-replica deployments (optional, Stage 11): InMemoryBucketStore is per-process only -- see Judgment calls
exposes:
  - BucketStore (Protocol), InMemoryBucketStore, RateLimitResult, check(store, key, *, capacity, refill_per_second, now=None), client_ip_key(remote_addr, forwarded_for, *, trust_proxy=False) -- in _core.py
  - fastapi.py: make_rate_limit_dependency(store, *, capacity, refill_per_second, key_func=None, trust_proxy=False), RateLimitMiddleware
  - django.py: RateLimitMiddleware (settings-configurable: RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_SECOND, RATE_LIMIT_TRUST_PROXY)
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
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
- Storage: pluggable, Redis stubbed for Stage 11
- The default key function and its proxy-trust posture
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
  (the stdlib implementation), `RateLimitResult` (`allowed`, `remaining`,
  `retry_after`), `check(store, key, *, capacity, refill_per_second,
  now=None)` (the convenience wrapper both adapters call),
  `client_ip_key(remote_addr, forwarded_for, *, trust_proxy=False)` (the
  default key function's logic) — all in `_core.py`.
- `fastapi.py`: `make_rate_limit_dependency(store, *, capacity,
  refill_per_second, key_func=None, trust_proxy=False)` (per-route),
  `RateLimitMiddleware` (whole-app).
- `django.py`: `RateLimitMiddleware`, configurable via `RATE_LIMIT_CAPACITY`
  / `RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUST_PROXY` settings or
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

## Storage: pluggable, Redis stubbed for Stage 11

`BucketStore` is a `Protocol` — `take(key, *, capacity, refill_per_second,
now) -> RateLimitResult`. `InMemoryBucketStore` is the stdlib
implementation this component ships (a `dict` + a `threading.Lock` for
atomicity within one process). **This module does not import `redis`** — a
Stage 11 Redis-backed `BucketStore` (atomic across multiple app processes
via a Lua script, unlike a Python-level lock) plugs into the exact same
Protocol without either framework adapter changing; that's the whole point
of the seam being a `Protocol` rather than `InMemoryBucketStore` being
hard-wired into `fastapi.py`/`django.py`.

## The default key function and its proxy-trust posture

`client_ip_key(remote_addr, forwarded_for, *, trust_proxy=False)` is
**PROXY-TRUSTED-ONLY**: `X-Forwarded-For` is a plain request header any
client can set to anything, so honoring it (`trust_proxy=True`) is only
correct once a project has confirmed its edge (ALB, CloudFront, a correctly
configured nginx/Caddy) strips or overwrites any inbound
`X-Forwarded-For` from the real client before appending its own hop.
Default is `trust_proxy=False` — `remote_addr` (the actual TCP peer) is
used and the header is ignored outright, which is safe everywhere but rate-
limits a proxy's own IP as if it were every client behind it if the app
genuinely sits behind an unconfirmed proxy. Both framework adapters thread
`trust_proxy` straight through to this function — set it to `True`
deliberately, per-environment, never as a blanket default.

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
`RATE_LIMIT_REFILL_PER_SECOND` / `RATE_LIMIT_TRUST_PROXY` from
`django.conf.settings` by default, falling back to `capacity=60`,
`refill_per_second=1.0`, `trust_proxy=False` if unset. Explicit constructor
kwargs (used throughout this component's own tests) override the
settings-derived value when passed, for a project wiring the middleware by
hand.

## Testing

`tests/test_core.py` covers the refill math with explicit deterministic
`now` values (first request allowed, burst-to-capacity then denied, exact
one-token-per-second refill, retry-after shrinking as elapsed time grows,
the bucket never exceeding `capacity`), per-key isolation, and every branch
of `client_ip_key`'s trust posture (XFF ignored by default, honored and
leftmost-entry-selected when trusted, falling back on an absent or blank
XFF even when trusted). `tests/test_fastapi.py` exercises both the
middleware and dependency variants against a real FastAPI `TestClient`
(allow-then-429, `Retry-After` present, an undecorated route unaffected by
a decorated one's drained bucket). `tests/test_django.py` exercises the
middleware via `RequestFactory` the same way, plus the XFF-ignored-by-
default vs. XFF-honored-when-`trust_proxy=True` behavior specifically
against `REMOTE_ADDR`/`HTTP_X_FORWARDED_FOR`.

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
  bucket key," a total bypass. Requiring an explicit `trust_proxy=True`
  opt-in, with the risk spelled out in the docstring right next to the
  parameter, matches secure-baseline's "deny by default, explicit opt-out"
  posture applied to a trust decision instead of an access decision.
