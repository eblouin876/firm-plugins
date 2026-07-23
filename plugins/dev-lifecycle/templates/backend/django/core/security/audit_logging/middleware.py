"""NEW GLUE — not a vendored file. `audit.py` (vendored from
templates/components/security/audit-logging/) exposes `bind_request_id()`/
`reset_request_id()` as a hook, documented in its own README as "for Step 3
middleware" but deliberately shipping no middleware itself (the component is
framework-neutral, and the FastAPI variant of this same glue —
backend/fastapi's app/core/security/audit_logging/middleware.py — is
ASGI-specific, not reusable here). This module is that Step 3 middleware
for the Django track: it binds a per-request id into audit.py's contextvar
at the top of every request and resets it at the end, so every
`audit_event()` call made anywhere downstream during that request — a
future Stage 5 login event, a service-layer action — automatically carries
the same id without threading it through every call site by hand.

Placed in this subpackage (alongside the vendored `audit.py` it composes)
rather than in config/settings.py directly, matching backend/fastapi's
audit_logging/middleware.py precedent for "new glue lives beside the
vendored pieces it wires together."

New-style Django middleware (`__init__(get_response)` / `__call__(request)`)
— Django has no pure-ASGI-only middleware contract the way Starlette does
(this middleware works identically whether config/asgi.py or
config/wsgi.py serves the request); there is no BaseHTTPMiddleware-style
buffering concern to avoid here the way there is on the FastAPI track.

See config/settings.py's MIDDLEWARE list and this block's README.md
"Security composition" section for where this sits in the middleware order
(inside security-headers, outside rate-limiting — "so every downstream
log/audit has the id," including a rate-limit denial's own audit trail if a
future stage adds one, since this middleware wraps rate-limiting).

**Divergence from the FastAPI track's equivalent, noted rather than
matched:** Django's `convert_exception_to_response` wraps every
middleware's `get_response` call, converting an unhandled exception into a
real `HttpResponse` (a 500) *before* it unwinds past this middleware — so
unlike backend/fastapi's `RequestIDMiddleware` (whose module docstring
documents the 500 path skipping its own `send_wrapper`, since Starlette's
`ServerErrorMiddleware` sits outside every `add_middleware()` layer), this
middleware's `response[...] = request_id` line DOES still run for a 500
response here. Both tracks still guarantee the same outcome
(`X-Request-ID` present on every response, including a 500) — they just
reach it via a different mechanism, which is exactly the kind of
Django-vs-Starlette plumbing difference this block's README documents
rather than papers over."""

from __future__ import annotations

import re
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from .audit import bind_request_id, reset_request_id

_REQUEST_ID_HEADER_META = "HTTP_X_REQUEST_ID"
_REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"

# A client-supplied X-Request-ID is a correlation id, not a security/trust
# decision like rate-limiting's X-Forwarded-For client-IP trust (see
# rate_limiting/_core.py's client_ip_key) — reflecting it back is safe and
# useful for tracing a request across a caller's own logs and this app's.
# It IS, however, still attacker-influenced input that ends up in a response
# header and (via bind_request_id) in every audit_event() JSON line for this
# request: bounding it to a short, printable-ASCII, no-whitespace/control-
# character shape before trusting it avoids a malformed or oversized header
# value reaching either place. A value that doesn't match this shape is
# treated as absent — a fresh id is minted instead of guessing at a
# sanitized version of it.
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _resolve_request_id(request: HttpRequest) -> str:
    inbound = request.META.get(_REQUEST_ID_HEADER_META)
    if inbound and _SAFE_REQUEST_ID_RE.match(inbound):
        return inbound
    return str(uuid.uuid4())


class RequestIDMiddleware:
    """Binds a request id (inbound `X-Request-ID` if present and
    shape-valid, otherwise a fresh `uuid4`) into audit.py's contextvar for
    the lifetime of one request, sets it on the outbound `X-Request-ID`
    response header, and unbinds it in a `finally` so a reused worker
    thread never leaks it into the next request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _resolve_request_id(request)
        request.request_id = request_id  # available to views/serializers, matching scope["state"] on the FastAPI track
        token = bind_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[_REQUEST_ID_RESPONSE_HEADER] = request_id
        return response
