"""Package seam for the vendored input-validation component (`validation.py`
— vendored from templates/components/security/input-validation/, see that
file's own header note). Same as audit_logging's `audit.py`: this component
ships as a single flat file with no cross-imports to adapt, so it needs no
relative-import rewrite and stays byte-identical below its header; it still
lands as its own subpackage for the same consistent-shape reason documented
in security_headers/__init__.py.

**DRF serializers stay DRF at the HTTP request boundary — this module is
NOT wired as that boundary's validation layer.** `core/serializers.py`'s
`ItemOut`/`ItemCreate`/`ItemUpdate` (and everything else in this block's
DRF contract-emission layer) remain what actually validates a request body;
`StrictModel`/the hardened field types below are for the shared/service
layer underneath both the FastAPI and Django/DRF tracks — business logic,
background job payload validation, or anywhere a Django project already
reaches for Pydantic for a non-DRF-request shape — per the component
README's "Django/DRF note". Nothing in this block's current step actually
calls into this subpackage yet (no shared/service layer exists here as of
Stage 4); it is vendored now, unused, so a later step composing one has it
available rather than needing a fresh vendoring pass.

Re-exports the names a future request/service-layer schema would need, so
a caller writes `from core.security.input_validation import StrictModel,
SafeText` instead of reaching into the vendored file directly.
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
