"""Package seam for the vendored cors-lockdown component (`_core.py`,
`django.py` — vendored from templates/components/security/cors-lockdown/,
see each file's own header note). Same relative-import composition pattern
as security_headers/__init__.py — see that file's docstring.

Re-exports the names config/settings.py needs to compose
`django-cors-headers`' settings from one `CORSPolicy` source of truth:
`from core.security.cors_lockdown import CORSPolicy, cors_settings`.
"""

from __future__ import annotations

from ._core import CORSPolicy, InsecureCORSPolicyError
from .django import CORS_MIDDLEWARE_CLASSPATH, REQUIRED_INSTALLED_APP, cors_settings

__all__ = [
    "CORSPolicy",
    "InsecureCORSPolicyError",
    "cors_settings",
    "CORS_MIDDLEWARE_CLASSPATH",
    "REQUIRED_INSTALLED_APP",
]
