"""Package seam for the vendored rate-limiting component (`_core.py`,
`django.py` — vendored from templates/components/security/rate-limiting/,
see each file's own header note). Same relative-import composition pattern
as security_headers/__init__.py — see that file's docstring.

Re-exports the names any in-app caller needs, so callers write
`from core.security.rate_limiting import InMemoryBucketStore` instead of
reaching into the individual vendored files. Django's own `MIDDLEWARE`
setting still takes the dotted-path STRING
(`"core.security.rate_limiting.django.RateLimitMiddleware"`), not an
import of the class itself — see config/settings.py.
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
from .django import RateLimitMiddleware

__all__ = [
    "BucketStore",
    "InMemoryBucketStore",
    "RateLimitResult",
    "check",
    "client_ip_key",
    "validate_refill_rate",
    "RateLimitMiddleware",
]
