"""Package seam for the vendored security-headers component (`_core.py`,
`fastapi.py` — vendored from templates/components/security/security-headers/,
see each file's own header note).

Same composition pattern as app/core/db/__init__.py: the source component
ships `fastapi.py` importing its core logic with a bare `import _core`
(a flat, directory-local sibling import — see that component's own README);
this app instead composes the directory as a real intra-package, with
`fastapi.py`'s cross-import rewritten to package-relative
(`from . import _core`) rather than a `sys.path` shim — see this app's
README.md "Vendored components" invariant. `_core.py` itself has no
cross-imports and stays byte-identical below its header.

Re-exports the names app/main.py's create_app() and any other in-app caller
need, so callers write `from app.core.security.security_headers import
SecurityHeadersPolicy, add_security_headers` instead of reaching into the
individual vendored files.
"""

from __future__ import annotations

from ._core import CSPPolicy, DEFAULT_POLICY, SecurityHeadersPolicy
from .fastapi import (
    SecurityHeadersMiddleware,
    add_security_headers,
    security_headers_dependency,
)

__all__ = [
    "CSPPolicy",
    "DEFAULT_POLICY",
    "SecurityHeadersPolicy",
    "SecurityHeadersMiddleware",
    "add_security_headers",
    "security_headers_dependency",
]
