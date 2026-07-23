"""Package seam for the vendored security-headers component (`_core.py`,
`django.py` — vendored from
templates/components/security/security-headers/, see each file's own
header note).

Same composition pattern as backend/fastapi's
app/core/security/security_headers/__init__.py: the source component ships
`django.py` importing its core logic with a bare `import _core` (a flat,
directory-local sibling import — see that component's own README); this app
instead composes the directory as a real intra-package, with `django.py`'s
cross-import rewritten to package-relative (`from . import _core`) rather
than a `sys.path` shim — see README.md's "Vendored components" invariant.
`_core.py` itself has no cross-imports and stays byte-identical below its
header.

Re-exports the names config/settings.py's MIDDLEWARE-adjacent wiring and any
other in-app caller need, so callers write `from
core.security.security_headers import SecurityHeadersPolicy` instead of
reaching into the individual vendored files. Django's own `MIDDLEWARE`
setting still takes the dotted-path STRING
(`"core.security.security_headers.django.SecurityHeadersMiddleware"`), not
an import of the class itself — see config/settings.py.
"""

from __future__ import annotations

from ._core import CSPPolicy, DEFAULT_POLICY, SecurityHeadersPolicy
from .django import SecurityHeadersMiddleware

__all__ = [
    "CSPPolicy",
    "DEFAULT_POLICY",
    "SecurityHeadersPolicy",
    "SecurityHeadersMiddleware",
]
