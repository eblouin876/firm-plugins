"""Django wiring for the rate-limiting component: a MIDDLEWARE class
returning 429 with a `Retry-After` header on deny. Canon:
references/security/secure-baseline.md ("Rate limiting & lockout").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/rate_limiting/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`.

Django only (`django`) -- no third-party dependency, no `redis` import.

Configuration reads Django settings (the Django convention), with an
explicit-kwarg override path for direct instantiation (used by this
component's own tests, and available to a project that wants to construct
this middleware itself rather than configure it via settings):
`RATE_LIMIT_CAPACITY` (default 60), `RATE_LIMIT_REFILL_PER_SECOND` (default
1.0), `RATE_LIMIT_TRUSTED_HOPS` (default 0) -- see `_core.py`'s
`client_ip_key` docstring for what that last one actually gates (0 = ignore
`X-Forwarded-For`, use the real peer address; an ALB directly in front of
the app is `RATE_LIMIT_TRUSTED_HOPS = 1`).
"""

from __future__ import annotations

import math
from typing import Callable

import _core
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

_default_store: _core.BucketStore | None = None


def _get_default_store() -> _core.BucketStore:
    """A module-level singleton store, created lazily on first use and
    shared by every request this process handles -- see _core.py's
    InMemoryBucketStore docstring for the per-process (not per-cluster)
    limitation this implies."""
    global _default_store
    if _default_store is None:
        _default_store = _core.InMemoryBucketStore()
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
    ) -> None:
        self.get_response = get_response
        self.store = store if store is not None else _get_default_store()
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

    def __call__(self, request: HttpRequest) -> HttpResponse:
        key = self.key_func(request)
        result = _core.check(
            self.store, key, capacity=self.capacity, refill_per_second=self.refill_per_second
        )
        if not result.allowed:
            response = JsonResponse({"detail": "rate limit exceeded"}, status=429)
            response["Retry-After"] = str(math.ceil(result.retry_after))
            return response
        return self.get_response(request)
