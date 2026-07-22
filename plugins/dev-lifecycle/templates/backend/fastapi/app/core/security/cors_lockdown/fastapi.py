# Vendored from templates/components/security/cors-lockdown (fastapi.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: `import _core` (bare sibling import) rewritten to `from . import _core`
# (package-relative) for in-app packaging — see app/core/db/__init__.py's
# docstring and README.md's "Vendored components" invariant. The rest of this
# file is unchanged: every other reference stays `_core.<name>`.

"""FastAPI/Starlette wiring for the cors-lockdown component: thin wiring of
Starlette's own `CORSMiddleware` from `_core.CORSPolicy`. Canon:
references/security/secure-baseline.md ("CORS lockdown").

Drop-in: copy this whole directory (this file, `_core.py`, `django.py`) into
app/core/security/cors_lockdown/ and keep them together. This file imports
its core logic with a bare `import _core` -- see `fastapi.py`'s counterpart
note in the security-headers component for why that's correct once these
files are copied into a project (not a relative `from . import _core`).

Starlette only (`starlette`, via the project's FastAPI install) -- no
third-party dependency beyond FastAPI itself. This module does not
reimplement CORS handling; it validates a policy and hands it straight to
Starlette's own `CORSMiddleware`, which does the actual preflight/simple-
request logic.
"""

from __future__ import annotations

from . import _core
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware


def add_cors(app: Starlette, policy: _core.CORSPolicy) -> None:
    """Wires `policy` into the app via Starlette's own `CORSMiddleware`.
    `policy` construction already rejected a wildcard-plus-anything
    configuration (see `_core.CORSPolicy.__post_init__`), so by the time
    this function runs there is nothing left to validate -- it is pure
    translation."""
    app.add_middleware(CORSMiddleware, **policy.to_starlette_kwargs())
