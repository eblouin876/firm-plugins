"""Security composition (Stage 3 #26, Step 3b): each subpackage here is a
self-contained vendored catalog component from
templates/components/security/, landed as its own Python subpackage with
relative imports only — no global `sys.path` manipulation — per the
INVARIANT app/core/db/__init__.py's docstring and README.md's "Vendored
components" section establish. See app/main.py's create_app() for how
these compose into the app's middleware stack, and this block's README.md
"Security composition" section for the full middleware-order rationale.

This file itself re-exports nothing — each subpackage below is imported
directly (`from app.core.security.security_headers import ...`, etc.) so a
caller only pulls in the one component it actually needs, matching
app/core/db's re-export pattern at the subpackage level rather than
flattening every security component's names into one shared namespace
here.
"""

from __future__ import annotations
