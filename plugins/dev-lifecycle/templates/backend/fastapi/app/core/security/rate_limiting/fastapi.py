# Vendored from templates/components/security/rate-limiting (fastapi.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: `import _core` (bare sibling import) rewritten to `from . import _core`
# (package-relative) for in-app packaging — see app/core/db/__init__.py's
# docstring and README.md's "Vendored components" invariant. The rest of this
# file is unchanged: every other reference stays `_core.<name>`.

"""FastAPI/Starlette wiring for the rate-limiting component: a dependency
variant (per-route) and a middleware variant (whole-app), both returning
429 with a `Retry-After` header on deny. Canon:
references/security/secure-baseline.md ("Rate limiting & lockout").

Drop-in: copy this whole directory (this file, `_core.py`, `django.py`)
into app/core/security/rate_limiting/ and keep them together. This file
imports its core logic with a bare `import _core` -- see the
security-headers component's `fastapi.py` for the full rationale.

Starlette/FastAPI only (`starlette`, `fastapi`) -- no third-party
dependency, no `redis` import (see `_core.py`'s module docstring).
"""

from __future__ import annotations

import math
from typing import Callable

from . import _core
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


def _default_key_func(request: Request, *, trusted_hops: int) -> str:
    remote_addr = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    return _core.client_ip_key(remote_addr, forwarded_for, trusted_hops=trusted_hops)


def make_rate_limit_dependency(
    store: _core.BucketStore,
    *,
    capacity: int,
    refill_per_second: float,
    key_func: Callable[[Request], str] | None = None,
    trusted_hops: int = 0,
) -> Callable:
    """Returns a FastAPI dependency for per-route rate limiting, e.g.:
    `@app.post("/login", dependencies=[Depends(make_rate_limit_dependency(
    store, capacity=5, refill_per_second=5/60))])` for a 5-per-minute login
    limit. `key_func`, if passed, receives the raw `Request` (not
    `trusted_hops` -- bind that with a lambda/partial if a custom key func
    also needs it) and must return the string key to bucket on.
    `trusted_hops` is threaded straight through to `_core.client_ip_key` --
    see its docstring; an ALB directly in front of the app is
    `trusted_hops=1`. Validates `refill_per_second` at construction time
    (see `_core.validate_refill_rate`) -- a misconfigured limiter fails
    loudly here, not on whichever request first gets denied."""
    _core.validate_refill_rate(refill_per_second)
    resolved_key_func = key_func or (lambda request: _default_key_func(request, trusted_hops=trusted_hops))

    async def rate_limit_dependency(request: Request) -> None:
        key = resolved_key_func(request)
        result = _core.check(store, key, capacity=capacity, refill_per_second=refill_per_second)
        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(math.ceil(result.retry_after))},
            )

    return rate_limit_dependency


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Whole-app rate limiting -- every request is bucketed, not just
    routes that opt in via the dependency above. Use this for a general
    per-IP API ceiling (secure-baseline's "apply a general API rate limit");
    use the dependency for a stricter per-endpoint limit layered on top
    (e.g. login gets both the general middleware limit AND its own tighter
    dependency limit)."""

    def __init__(
        self,
        app,
        *,
        store: _core.BucketStore,
        capacity: int,
        refill_per_second: float,
        key_func: Callable[[Request], str] | None = None,
        trusted_hops: int = 0,
    ) -> None:
        _core.validate_refill_rate(refill_per_second)
        super().__init__(app)
        self.store = store
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.key_func = key_func or (lambda request: _default_key_func(request, trusted_hops=trusted_hops))

    async def dispatch(self, request: Request, call_next):
        key = self.key_func(request)
        result = _core.check(
            self.store, key, capacity=self.capacity, refill_per_second=self.refill_per_second
        )
        if not result.allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(math.ceil(result.retry_after))},
            )
        return await call_next(request)
