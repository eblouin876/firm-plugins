"""Package seam for the vendored input-validation component (`validation.py`
— vendored from templates/components/security/input-validation/, see that
file's own header note). Same as secret_store/ and audit_logging/'s
`audit.py`: this component ships as a single flat file with no
cross-imports to adapt, so it needs no relative-import rewrite and stays
byte-identical below its header; it still lands as its own subpackage for
the same consistent-shape reason documented in secret_store/__init__.py.

Re-exports the names a request/service-layer schema needs so callers write
`from app.core.security.input_validation import StrictModel, SafeText`
instead of reaching into the vendored file directly.
"""

from __future__ import annotations

from .validation import (
    Email,
    SafeFilename,
    SafeIdentifier,
    SafeText,
    ShortStr,
    Slug,
    StrictModel,
    check_max_bytes,
    check_max_length,
    no_control_chars,
    safe_filename,
)

__all__ = [
    "Email",
    "SafeFilename",
    "SafeIdentifier",
    "SafeText",
    "ShortStr",
    "Slug",
    "StrictModel",
    "check_max_bytes",
    "check_max_length",
    "no_control_chars",
    "safe_filename",
]
