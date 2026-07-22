# Vendored from templates/components/security/rate-limiting (_core.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.

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

**`X-Forwarded-For` semantics, corrected:** an edge proxy (ALB, CloudFront,
a correctly configured nginx/Caddy) APPENDS its observed peer address to
`X-Forwarded-For` when forwarding a request -- it does NOT strip or
overwrite whatever the client already put in that header. A client can set
`X-Forwarded-For` to anything; only entries appended by proxies YOU control
are trustworthy. `client_ip_key`'s `trusted_hops` parameter (see its own
docstring) selects the entry counting from the RIGHT end of the header by
the number of trusted hops -- never the leftmost entry, which is fully
client-controlled and was the exploitable bug this docstring used to
recommend without saying so."""

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

    Known limitations, documented rather than hidden:

    - **Per-process.** A multi-worker WSGI/ASGI deployment (gunicorn with N
      workers, multiple ECS tasks) gives each worker/process its own
      independent bucket for the same key -- the *effective* rate limit
      becomes roughly N times the configured `capacity`/`refill_per_second`,
      not a hard shared ceiling. Acceptable for a single-process dev server
      or a single-replica deployment; a project running multiple workers/
      replicas that needs a true shared ceiling needs the Redis-backed
      `BucketStore` (Stage 11), not this one. See the component README's
      "Judgment calls".
    - **Bounded by idle-eviction and an optional key cap, not unbounded.**
      Every `take()` sweeps buckets idle beyond `ttl_seconds` (default
      900s / 15 minutes -- a key that hasn't been touched in that long has
      no meaningful rate-limit state worth keeping: its bucket would have
      fully refilled to `capacity` long before, so evicting it changes
      nothing observable). Without this, a key space with high cardinality
      (e.g. per-IP keys under a churn of many distinct clients) would grow
      this dict without bound -- an unbounded-memory-growth risk.
      `max_keys` (default `None` -- disabled) additionally caps the total
      number of buckets regardless of idle time, evicting the single
      oldest-by-`last_seen` bucket whenever a `take()` would exceed the
      cap. Both are per-process, like everything else about this store."""

    def __init__(
        self, *, ttl_seconds: float = 900.0, max_keys: int | None = None
    ) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_seen)
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        self.max_keys = max_keys

    def take(
        self, key: str, *, capacity: int, refill_per_second: float, now: float
    ) -> RateLimitResult:
        with self._lock:
            self._evict_idle(now)
            tokens, last_seen = self._buckets.get(key, (float(capacity), now))
            elapsed = max(0.0, now - last_seen)
            tokens = min(float(capacity), tokens + elapsed * refill_per_second)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                result = RateLimitResult(allowed=True, remaining=tokens, retry_after=0.0)
            else:
                deficit = 1.0 - tokens
                retry_after = deficit / refill_per_second if refill_per_second > 0 else float("inf")
                self._buckets[key] = (tokens, now)
                result = RateLimitResult(allowed=False, remaining=tokens, retry_after=retry_after)
            if self.max_keys is not None:
                self._evict_oldest_over_cap(keep=key)
            return result

    def _evict_idle(self, now: float) -> None:
        """Removes every bucket idle beyond `ttl_seconds`. A no-op when
        `ttl_seconds <= 0` (an explicit "never expire" opt-out)."""
        if self.ttl_seconds <= 0:
            return
        stale_keys = [k for k, (_, last_seen) in self._buckets.items() if now - last_seen > self.ttl_seconds]
        for k in stale_keys:
            del self._buckets[k]

    def _evict_oldest_over_cap(self, *, keep: str) -> None:
        """Removes the oldest-by-`last_seen` bucket(s) until at or under
        `max_keys`, never evicting `keep` (the bucket `take()` just
        touched -- a cap of 1 must not immediately evict it)."""
        while len(self._buckets) > self.max_keys:  # type: ignore[operator]
            oldest_key = min(
                (k for k in self._buckets if k != keep),
                key=lambda k: self._buckets[k][1],
                default=None,
            )
            if oldest_key is None:
                break
            del self._buckets[oldest_key]


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


def client_ip_key(remote_addr: str, forwarded_for: str | None, *, trusted_hops: int = 0) -> str:
    """The default rate-limit key function: the caller's IP address.

    **`trusted_hops` selects rightmost-minus-N, never the leftmost entry.**
    `X-Forwarded-For` is APPENDED to by each proxy hop, not overwritten --
    a client can set the header to any value it likes, and a proxy in front
    of the app adds its own observed peer address to the RIGHT end of
    whatever was already there. That means the only entries an app can
    trust are the ones its OWN trusted proxies appended -- counting from the
    right, by exactly the number of trusted proxies in front of the app.

    - `trusted_hops=0` (the default): ignore `X-Forwarded-For` entirely,
      use `remote_addr` (the actual TCP peer) -- safe everywhere, including
      with no proxy at all or an unconfirmed/untrusted proxy config. This
      rate-limits the proxy's own IP as if it were every client behind it
      if the app genuinely sits behind a proxy this wasn't configured for.
    - `trusted_hops=N` (`N >= 1`): take the Nth-from-right entry in
      `X-Forwarded-For` -- the address the OUTERMOST of the N trusted
      proxies in front of this app saw when it received the request. A
      single edge proxy directly in front of the app (e.g. an AWS ALB with
      nothing else in front of it) is `trusted_hops=1`: the rightmost
      entry, appended by that ALB, is the address it actually saw the
      connection from. A project MUST set `trusted_hops` to the exact
      number of trusted proxies it controls, deliberately, per-environment
      -- never guessed, and never a value greater than the number of
      proxies actually in front of the app (that would trust an entry the
      client itself could have supplied).

    If `X-Forwarded-For` has FEWER entries than `trusted_hops` (a
    malformed or missing header from what should be a trusted proxy chain),
    this falls back to `remote_addr` rather than guessing -- an
    insufficient header is treated as "cannot verify", not "trust
    whatever's leftmost".

    Blank entries in the header (e.g. `", 10.0.0.1"`, a comma with nothing
    before it) are dropped before counting from the right."""
    if trusted_hops <= 0 or not forwarded_for:
        return remote_addr
    entries = [entry.strip() for entry in forwarded_for.split(",")]
    entries = [entry for entry in entries if entry]
    if len(entries) < trusted_hops:
        return remote_addr
    return entries[-trusted_hops]


def validate_refill_rate(refill_per_second: float) -> None:
    """Raises `ValueError` if `refill_per_second <= 0`. A bucket that never
    refills isn't a token bucket at all, and letting it through has a real
    crash consequence: on deny, `retry_after` is computed as
    `deficit / refill_per_second`, which is `float("inf")` when
    `refill_per_second == 0` (and meaningless/negative for a negative rate)
    -- both framework adapters then call `math.ceil(result.retry_after)` to
    build the `Retry-After` header, and `math.ceil(float("inf"))` raises
    `OverflowError`, turning an intended 429 response into an unhandled 500.
    Both framework adapters call this at CONSTRUCTION time (the dependency
    factory / middleware `__init__`), not per-request, so a misconfigured
    limiter fails loudly at startup rather than on whichever request
    happens to first get denied. For a "fixed N requests, never refills"
    quota instead of a token bucket, build that pattern separately (e.g. a
    plain counter with its own reset schedule) rather than passing
    `refill_per_second<=0` here."""
    if refill_per_second <= 0:
        raise ValueError(
            "refill_per_second must be > 0 -- a bucket that never refills isn't "
            "a token bucket (and produces retry_after=inf, which crashes the "
            "Retry-After header's math.ceil() with OverflowError instead of "
            "returning 429). For a fixed-quota-then-blocked pattern, build that "
            "separately rather than using this limiter with refill_per_second<=0."
        )
