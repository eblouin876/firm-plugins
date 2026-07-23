"""Security composition (Stage 4 Step 3, #27): each subpackage here is a
self-contained vendored catalog component from
templates/components/security/, landed as its own Python subpackage with
relative imports only — no global `sys.path` manipulation — mirroring the
INVARIANT backend/fastapi's app/core/security/__init__.py establishes for
that track (and app/core/db/__init__.py's precedent before it). See
config/settings.py's MIDDLEWARE list for how these compose into this app's
middleware stack, and this block's README.md "Security composition" section
for the full middleware-order rationale (including where Django's own
process_request/process_response order diverges from Starlette's ASGI
onion, which is why this track's MIDDLEWARE order isn't a copy-paste of
backend/fastapi's `create_app()` call order).

`secret_store` is NOT a subpackage here — it was already vendored at
`core/contract/secret_store.py` in Stage 4 Step 1, and this step reuses
that copy rather than vendoring a second one; see README.md's "Security
composition" section, "secret_store: one copy, not two" for the dedup
rationale. `input_validation` IS a subpackage here (framework-neutral,
no django.py) even though DRF serializers remain the actual HTTP
request-validation layer — see input_validation/__init__.py's docstring.

This file itself re-exports nothing — each subpackage below is imported
directly (`from core.security.security_headers.django import
SecurityHeadersMiddleware`, etc. — Django's own MIDDLEWARE setting takes a
dotted string, not an import) so a caller only pulls in the one component
it actually needs.
"""

from __future__ import annotations
