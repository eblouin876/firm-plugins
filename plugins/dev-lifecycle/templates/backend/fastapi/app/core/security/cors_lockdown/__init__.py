"""Package seam for the vendored cors-lockdown component (`_core.py`,
`fastapi.py` — vendored from templates/components/security/cors-lockdown/,
see each file's own header note). Same relative-import composition pattern
as security_headers/__init__.py — see that file's docstring.

Re-exports the names app/main.py's create_app() needs so callers write
`from app.core.security.cors_lockdown import CORSPolicy, add_cors` instead
of reaching into the individual vendored files.
"""

from __future__ import annotations

from ._core import CORSPolicy, InsecureCORSPolicyError
from .fastapi import add_cors

__all__ = ["CORSPolicy", "InsecureCORSPolicyError", "add_cors"]
