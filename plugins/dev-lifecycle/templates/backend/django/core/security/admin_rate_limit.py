"""Stage 13b: a tighter, PER-ROUTE rate limit for the admin user-management
surface (`core/views.py`'s `AdminUser*View` classes) -- layered on top of
the general per-IP `RateLimitMiddleware` (`core/security/rate_limiting/
django.py`) every request already goes through, the SAME "the admin surface
is the highest-value target" posture `app/api/routers/admin.py`'s FastAPI
counterpart documents for its own `require_admin_rate_limit`.

**NOT a vendored file** -- app code, same posture `core/security/auth/
stores.py`'s own module docstring documents for that file: it imports the
vendored rate-limiting component's `_core` module directly (`check`,
`InMemoryBucketStore`, `client_ip_key`, all already re-exported by
`core/security/rate_limiting/__init__.py`) but adds no new rate-limiting
LOGIC of its own -- this is a second, distinct BUCKET than the whole-app
middleware's own, not a second implementation.

There is no Django/DRF equivalent of `templates/components/security/
rate-limiting/fastapi.py`'s `make_rate_limit_dependency` (a per-route
dependency factory) in the vendored component catalog -- only a whole-app
MIDDLEWARE class is vendored for Django (`core/security/rate_limiting/
django.py`'s own module docstring: "a MIDDLEWARE class"). `enforce_admin_
rate_limit` below is this app's own minimal per-call-site equivalent,
built directly against the same `_core.check`/`InMemoryBucketStore`
primitives the middleware itself uses."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from core.contract.errors import RateLimitedError
from core.security.rate_limiting import InMemoryBucketStore, check, client_ip_key

# Module-level singleton, shared by every admin request this process
# handles -- the identical "one bucket per client IP, not one per request"
# property `core/security/rate_limiting/django.py`'s own `_default_store`
# has for the whole-app middleware. 30 requests/minute is a starting-point
# default (not load-tested), deliberately tighter than `settings.
# RATE_LIMIT_CAPACITY`'s own 60/minute default -- tune per project.
_ADMIN_RATE_LIMIT_STORE = InMemoryBucketStore(max_keys=10_000)
_ADMIN_RATE_LIMIT_CAPACITY = 30
_ADMIN_RATE_LIMIT_REFILL_PER_SECOND = 30 / 60


def reset_admin_rate_limit_store_for_tests() -> None:
    """Test-only hook, mirroring `core/security/rate_limiting/django.py`'s
    own module-level `_default_store` reset that `tests/conftest.py`'s
    `_reset_rate_limit_store` fixture already relies on -- reassigns the
    module-level name (unlike the FastAPI track's equivalent, which must
    mutate a store already captured by an import-time closure -- see that
    module's own comment on why -- `enforce_admin_rate_limit` below reads
    `_ADMIN_RATE_LIMIT_STORE` as a plain global lookup on EVERY call, so a
    reassignment here is seen immediately)."""
    global _ADMIN_RATE_LIMIT_STORE
    _ADMIN_RATE_LIMIT_STORE = InMemoryBucketStore(max_keys=10_000)


def enforce_admin_rate_limit(request: Any) -> None:
    """Call at the top of every admin user-management view's handler
    (`core/views.py`) -- raises `RateLimitedError` (429 `rate_limited`, via
    `core.exceptions.exception_handler`'s `AppError` branch) when this
    client's admin-surface bucket is exhausted. `client_ip_key` reads the
    SAME `settings.RATE_LIMIT_TRUSTED_HOPS` the whole-app middleware itself
    reads (`core/security/rate_limiting/django.py`) -- one project-wide
    proxy-trust posture, not a second, possibly-drifted one for this
    tighter bucket."""
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    trusted_hops = getattr(settings, "RATE_LIMIT_TRUSTED_HOPS", 0)
    key = client_ip_key(remote_addr, forwarded_for, trusted_hops=trusted_hops)
    result = check(
        _ADMIN_RATE_LIMIT_STORE,
        key,
        capacity=_ADMIN_RATE_LIMIT_CAPACITY,
        refill_per_second=_ADMIN_RATE_LIMIT_REFILL_PER_SECOND,
    )
    if not result.allowed:
        raise RateLimitedError()
