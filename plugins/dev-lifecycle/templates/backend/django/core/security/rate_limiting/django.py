# Vendored from templates/components/security/rate-limiting (django.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: `import _core` (bare sibling import) rewritten to `from . import _core`
# (package-relative) for in-app packaging — see this block's README.md
# "Vendored components" invariant. The docstring's "copy this whole
# directory" line also dropped `fastapi.py` from its file list (this block
# never vendors the FastAPI adapter) -- declared here, not silently edited,
# so the freshness audit doesn't misflag it as an undocumented drop.
# DRIFT (Stage 4 Step 3 review fix, #27): two THIS-APP-SPECIFIC additions
# below the canonical component body, both flagged inline where they land:
# (1) `/health`/`/readyz` are exempt from rate limiting (`_DEFAULT_EXEMPT_
# PATHS`, `__call__`'s early-return) -- a readiness/liveness probe must
# never be rate-limited into a false-unhealthy signal at a load balancer
# that polls it far more often than `RATE_LIMIT_CAPACITY` allows (an edge
# proxy sitting in front of this app at `RATE_LIMIT_TRUSTED_HOPS=0` would
# 429 its own health checks under burst, reading as an outage). This is a
# per-app policy choice, not a general component feature -- the canonical
# `templates/components/security/rate-limiting/django.py` has no such
# exemption, and `backend/fastapi`'s `RateLimitMiddleware` still rate-limits
# its own `/health` too (flagged as a cross-track follow-up in this PR's
# decision log, not fixed there). (2) `RATE_LIMIT_MAX_KEYS` is threaded into
# the default store's construction (see `_get_default_store` below) --
# `_core.InMemoryBucketStore` already supports a `max_keys` bound
# (`_core.py`'s own docstring); this block just wires a Django setting to
# it so the per-process key cardinality is bounded by default rather than
# left at the component's own `None` (unbounded, idle-TTL-only) default.

"""Django wiring for the rate-limiting component: a MIDDLEWARE class
returning 429 with a `Retry-After` header on deny. Canon:
references/security/secure-baseline.md ("Rate limiting & lockout").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/rate_limiting/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`
(this app doesn't vendor `fastapi.py` itself -- see the DRIFT note above).

Django only (`django`) -- no third-party dependency, no `redis` import.

Configuration reads Django settings (the Django convention), with an
explicit-kwarg override path for direct instantiation (used by this
component's own tests, and available to a project that wants to construct
this middleware itself rather than configure it via settings):
`RATE_LIMIT_CAPACITY` (default 60), `RATE_LIMIT_REFILL_PER_SECOND` (default
1.0), `RATE_LIMIT_TRUSTED_HOPS` (default 0) -- see `_core.py`'s
`client_ip_key` docstring for what that last one actually gates (0 = ignore
`X-Forwarded-For`, use the real peer address; an ALB directly in front of
the app is `RATE_LIMIT_TRUSTED_HOPS = 1`). `RATE_LIMIT_MAX_KEYS` (default
50_000) and the `/health`+`/readyz` exemption are this app's own additions,
not canonical to the component -- see the DRIFT note above.
"""

from __future__ import annotations

import math
from typing import Callable

from . import _core
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

# This app's own default -- not a canonical component constant, see the
# module DRIFT note above. `_core.InMemoryBucketStore`'s own default is
# `max_keys=None` (unbounded, idle-TTL-eviction only); 50_000 buckets is a
# generous per-process cap for a per-client-IP key space that still bounds
# worst-case memory under a high-cardinality-client burst.
_DEFAULT_MAX_KEYS = 50_000

# This app's own default -- not a canonical component constant, see the
# module DRIFT note above. A readiness/liveness probe must never be gated
# by the same bucket as ordinary traffic.
_DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/readyz"})

_default_store: _core.BucketStore | None = None


def _get_default_store(*, max_keys: int | None) -> _core.BucketStore:
    """A module-level singleton store, created lazily on first use and
    shared by every request this process handles -- see _core.py's
    InMemoryBucketStore docstring for the per-process (not per-cluster)
    limitation this implies. `max_keys` only takes effect the FIRST time
    this creates the singleton in a given process -- a later call with a
    different value has no effect on an already-constructed store (matches
    every other setting this middleware reads: read once, at whichever
    request first triggers construction)."""
    global _default_store
    if _default_store is None:
        _default_store = _core.InMemoryBucketStore(max_keys=max_keys)
    return _default_store


def _default_key_func(request: HttpRequest, *, trusted_hops: int) -> str:
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return _core.client_ip_key(remote_addr, forwarded_for, trusted_hops=trusted_hops)


class RateLimitMiddleware:
    """New-style Django middleware. Django instantiates `MIDDLEWARE`
    entries with only `get_response` (no way to pass constructor kwargs
    from `settings.MIDDLEWARE` itself), so configuration beyond
    `get_response` is read from `django.conf.settings` by default --
    explicit kwargs (used by this component's tests, and available to a
    project wiring the middleware by hand instead of via `MIDDLEWARE=[...]`)
    override the settings-derived value when passed."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
        *,
        store: _core.BucketStore | None = None,
        capacity: int | None = None,
        refill_per_second: float | None = None,
        key_func: Callable[[HttpRequest], str] | None = None,
        trusted_hops: int | None = None,
        max_keys: int | None = None,
        exempt_paths: frozenset[str] | None = None,
    ) -> None:
        self.get_response = get_response
        resolved_max_keys = max_keys if max_keys is not None else getattr(settings, "RATE_LIMIT_MAX_KEYS", _DEFAULT_MAX_KEYS)
        self.store = store if store is not None else _get_default_store(max_keys=resolved_max_keys)
        self.capacity = capacity if capacity is not None else getattr(settings, "RATE_LIMIT_CAPACITY", 60)
        self.refill_per_second = (
            refill_per_second
            if refill_per_second is not None
            else getattr(settings, "RATE_LIMIT_REFILL_PER_SECOND", 1.0)
        )
        _core.validate_refill_rate(self.refill_per_second)
        resolved_trusted_hops = (
            trusted_hops if trusted_hops is not None else getattr(settings, "RATE_LIMIT_TRUSTED_HOPS", 0)
        )
        self.key_func = key_func or (
            lambda request: _default_key_func(request, trusted_hops=resolved_trusted_hops)
        )
        # `/health`/`/readyz` (this app's readiness/liveness probes) are
        # never rate-limited -- see the module DRIFT note above for why.
        self.exempt_paths = (
            exempt_paths if exempt_paths is not None else frozenset(getattr(settings, "RATE_LIMIT_EXEMPT_PATHS", _DEFAULT_EXEMPT_PATHS))
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path in self.exempt_paths:
            return self.get_response(request)
        key = self.key_func(request)
        result = _core.check(
            self.store, key, capacity=self.capacity, refill_per_second=self.refill_per_second
        )
        if not result.allowed:
            response = JsonResponse({"detail": "rate limit exceeded"}, status=429)
            response["Retry-After"] = str(math.ceil(result.retry_after))
            return response
        return self.get_response(request)
