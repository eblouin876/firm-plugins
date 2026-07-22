"""NEW GLUE — not a vendored file. `audit.py` (vendored from
templates/components/security/audit-logging/) exposes `bind_request_id()`/
`reset_request_id()` as a hook, documented in its own README as "for Step 3
middleware" but deliberately shipping no middleware itself (the component is
framework-neutral). This module is that Step 3 middleware for FastAPI: it
binds a per-request id into audit.py's contextvar at the top of every
request and resets it at the end, so every `audit_event()` call made
anywhere downstream during that request — a future Stage 5 login event, a
service-layer action — automatically carries the same id without threading
it through every call site by hand.

Placed in this subpackage (alongside the vendored `audit.py` it composes)
rather than in app/main.py directly, matching app/core/db/__init__.py's
precedent for "new glue lives beside the vendored pieces it wires together."

Pure-ASGI (not BaseHTTPMiddleware) for the same reason security_headers/
fastapi.py's SecurityHeadersMiddleware is: setting/reading one header is not
worth buffering the whole response body for.

See app/main.py's create_app() for where this sits in the middleware order
(between rate-limiting and security-headers — "so every downstream log/
audit has the id," including a rate-limit denial's own audit trail if a
future stage adds one, since this middleware wraps rate-limiting)."""

from __future__ import annotations

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .audit import bind_request_id, reset_request_id

_REQUEST_ID_HEADER = b"x-request-id"

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


def _resolve_request_id(scope: Scope) -> str:
    inbound: str | None = None
    for name, value in scope.get("headers", []):
        if name == _REQUEST_ID_HEADER:
            inbound = value.decode("latin-1")
            break
    if inbound and _SAFE_REQUEST_ID_RE.match(inbound):
        return inbound
    return str(uuid.uuid4())


class RequestIDMiddleware:
    """Binds a request id (inbound `X-Request-ID` if present and
    shape-valid, otherwise a fresh `uuid4`) into audit.py's contextvar for
    the lifetime of one request, sets it on the outbound `X-Request-ID`
    response header, and unbinds it in a `finally` so a reused worker
    task never leaks it into the next request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        scope["state"] = {**scope.get("state", {}), "request_id": request_id}
        token = bind_request_id(request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                raw_headers.append((_REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            reset_request_id(token)
