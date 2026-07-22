"""Package seam for the vendored audit-logging component (`audit.py` —
vendored from templates/components/security/audit-logging/, see that file's
own header note) plus `middleware.py`, this app's NEW (non-vendored)
FastAPI request-id binding glue — see that file's own module docstring for
why it lives here.

`audit.py` ships as a single flat file with no cross-imports to adapt, so
(like secret_store/) it needs no relative-import rewrite and stays
byte-identical below its header.

Re-exports the names app/main.py's create_app() and any future call site
need, so callers write `from app.core.security.audit_logging import
audit_event, RequestIDMiddleware` instead of reaching into the individual
files.
"""

from __future__ import annotations

from .audit import (
    DEFAULT_SENSITIVE_KEYS,
    REDACTED,
    audit_event,
    bind_request_id,
    redact,
    request_id_var,
    reset_request_id,
)
from .middleware import RequestIDMiddleware

__all__ = [
    "DEFAULT_SENSITIVE_KEYS",
    "REDACTED",
    "audit_event",
    "bind_request_id",
    "redact",
    "request_id_var",
    "reset_request_id",
    "RequestIDMiddleware",
]
