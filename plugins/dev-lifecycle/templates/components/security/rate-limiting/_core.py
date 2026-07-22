"""Framework-neutral token-bucket rate limiter: pluggable storage (a
`BucketStore` Protocol, with a stdlib in-memory implementation included), a
default client-IP key function with a documented proxy-trust posture, and
the allow/deny + retry-after result both framework adapters build a 429
response from. Canon: references/security/secure-baseline.md ("Rate
limiting & lockout" — rate-limit auth endpoints and any expensive/abuse-
prone action, apply a general per-user/per-IP limit, return 429 with
Retry-After).

Drop-in: copy this file into app/core/security/rate_limiting/_core.py (keep
it alongside fastapi.py/django.py from the same directory). Stdlib only.

A Redis-backed `BucketStore` is Stage 11 work (see the component README) --
this module deliberately does NOT import `redis`. The `BucketStore` Protocol
below is exactly the seam a Redis implementation (using a Lua script for
atomicity across processes, unlike this module's in-memory store) plugs
into without this file or either framework adapter changing.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The outcome of one `BucketStore.take()` call. `retry_after` is
    always present (0.0 when allowed) so a caller never has to branch on
    `allowed` before reading it -- both framework adapters set the
    `Retry-After` response header directly from this field only on the
    deny path, but the field itself is unconditional."""

    allowed: bool
    remaining: float
    retry_after: float


class BucketStore(Protocol):
    """The storage seam a rate limiter's state lives behind. `take()` must
    be atomic per key under concurrent callers -- `InMemoryBucketStore`
    below achieves that with a `threading.Lock`; a Redis-backed
    implementation (Stage 11) would use a Lua script (INCR+PEXPIRE or a
    proper token-bucket script) for the same atomicity across multiple
    app processes, which no single-process lock can provide."""

    def take(
        self, key: str, *, capacity: int, refill_per_second: float, now: float
    ) -> RateLimitResult: ...


class InMemoryBucketStore:
    """Stdlib-only in-memory token bucket, one bucket per key, refilled
    lazily at access time (no background timer/thread) -- the bucket's
    token count is only ever computed when `take()` is actually called, by
    multiplying elapsed time since the last call by `refill_per_second`.

    Known limitation, documented rather than hidden: this store is
    per-process. A multi-worker WSGI/ASGI deployment (gunicorn with N
    workers, multiple ECS tasks) gives each worker/process its own
    independent bucket for the same key -- the *effective* rate limit
    becomes roughly N times the configured `capacity`/`refill_per_second`,
    not a hard shared ceiling. Acceptable for a single-process dev server
    or a single-replica deployment; a project running multiple workers/
    replicas that needs a true shared ceiling needs the Redis-backed
    `BucketStore` (Stage 11), not this one. See the component README's
    "Judgment calls"."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_seen)
        self._lock = threading.Lock()

    def take(
        self, key: str, *, capacity: int, refill_per_second: float, now: float
    ) -> RateLimitResult:
        with self._lock:
            tokens, last_seen = self._buckets.get(key, (float(capacity), now))
            elapsed = max(0.0, now - last_seen)
            tokens = min(float(capacity), tokens + elapsed * refill_per_second)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return RateLimitResult(allowed=True, remaining=tokens, retry_after=0.0)
            deficit = 1.0 - tokens
            retry_after = deficit / refill_per_second if refill_per_second > 0 else float("inf")
            self._buckets[key] = (tokens, now)
            return RateLimitResult(allowed=False, remaining=tokens, retry_after=retry_after)


def check(
    store: BucketStore,
    key: str,
    *,
    capacity: int,
    refill_per_second: float,
    now: float | None = None,
) -> RateLimitResult:
    """Convenience wrapper: `now` defaults to `time.monotonic()`
    (deliberately not `time.time()` -- wall-clock adjustments/NTP jumps
    must never affect refill math; both framework adapters call this
    unqualified, and tests inject an explicit `now` for deterministic
    refill-math assertions)."""
    resolved_now = now if now is not None else time.monotonic()
    return store.take(key, capacity=capacity, refill_per_second=refill_per_second, now=resolved_now)


def client_ip_key(remote_addr: str, forwarded_for: str | None, *, trust_proxy: bool = False) -> str:
    """The default rate-limit key function: the caller's IP address.

    **PROXY-TRUSTED-ONLY**: `X-Forwarded-For` is a plain request header --
    any client can set it to an arbitrary value. Honoring it
    (`trust_proxy=True`) is only correct when the app is deployed behind a
    proxy/load balancer this project controls, one that itself overwrites
    or strips any inbound `X-Forwarded-For` from the original client before
    appending its own hop (ALB/CloudFront do this correctly by default;
    a bare nginx/Caddy config might not, and must be checked). With
    `trust_proxy=False` (the default), `forwarded_for` is ignored entirely
    and `remote_addr` (the actual TCP peer -- the proxy itself, in a
    proxied deployment) is used -- safe everywhere, but rate-limits the
    proxy's own IP as if it were every client behind it if the app truly is
    behind an untrusted-config proxy. A project MUST set `trust_proxy=True`
    deliberately, only once it has confirmed its edge strips/overwrites
    client-supplied `X-Forwarded-For`, never as the default.

    When trusted, the LEFTMOST entry in a comma-separated
    `X-Forwarded-For` is used (closest to the original client, per the
    header's own append-only-at-each-hop convention) -- not the rightmost,
    which is the proxy's own immediate remote address and defeats the
    point of reading the header at all."""
    if trust_proxy and forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return remote_addr
