"""Django wiring for the cors-lockdown component: a config EMITTER, not a
middleware. Django's own CORS convention is the third-party
`django-cors-headers` package (see the component README's NEEDS) -- this
module's job is turning `_core.CORSPolicy` into the settings dict that
package reads, not reimplementing what it already does well. Canon:
references/security/secure-baseline.md ("CORS lockdown").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/cors_lockdown/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py`.

Django only (`django`) for the settings-merge helper below -- `corsheaders`
itself is declared as a NEEDS, not imported here: this module never imports
`django-cors-headers`, it only emits the dict of settings names that
package's own middleware reads, so a project that hasn't installed the
package yet can still import this file without an ImportError.
"""

from __future__ import annotations

from typing import Any

import _core


def cors_settings(policy: _core.CORSPolicy) -> dict[str, Any]:
    """Returns the `django-cors-headers` settings dict for `policy`. Merge
    into settings.py with `globals().update(cors_settings(policy))` (or
    assign each key individually) -- this function does not touch
    `django.conf.settings` itself, since Django settings are conventionally
    plain module-level names in settings.py, not runtime-mutable after
    startup."""
    return policy.to_django_cors_headers_settings()


# The exact `MIDDLEWARE` entry and its required placement -- corsheaders'
# own docs require CorsMiddleware to run as early as possible, and
# specifically BEFORE Django's CommonMiddleware (which can issue a redirect
# response that never reaches corsheaders' own middleware for header
# injection if placed after it).
CORS_MIDDLEWARE_CLASSPATH = "corsheaders.middleware.CorsMiddleware"
REQUIRED_INSTALLED_APP = "corsheaders"
