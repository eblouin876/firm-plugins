"""Package seam for the vendored rate-limiting component (`_core.py`,
`fastapi.py` — vendored from templates/components/security/rate-limiting/,
see each file's own header note). Same relative-import composition pattern
as security_headers/__init__.py — see that file's docstring.

Re-exports the names app/main.py's create_app() and any per-route caller
need so callers write `from app.core.security.rate_limiting import
RateLimitMiddleware, InMemoryBucketStore` instead of reaching into the
individual vendored files.
"""

from __future__ import annotations

from ._core import (
    BucketStore,
    InMemoryBucketStore,
    RateLimitResult,
    check,
    client_ip_key,
    validate_refill_rate,
)
from .fastapi import RateLimitMiddleware, make_rate_limit_dependency

__all__ = [
    "BucketStore",
    "InMemoryBucketStore",
    "RateLimitResult",
    "check",
    "client_ip_key",
    "validate_refill_rate",
    "RateLimitMiddleware",
    "make_rate_limit_dependency",
]
