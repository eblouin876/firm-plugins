"""FastAPI/Starlette wiring for the security-headers component: a pure-ASGI
middleware that sets the header set `_core.SecurityHeadersPolicy` builds on
every outbound response. Canon: references/security/secure-baseline.md
("Security headers & CSP").

Drop-in: copy this whole directory (this file, `_core.py`, `django.py`) into
app/core/security/security_headers/ and keep them together. This file
imports its core logic with a bare `import _core` (not a relative `from .
import _core`) — that only resolves correctly when this file and `_core.py`
sit as siblings on the Python import path, which is exactly how they're
copied in. If a project's layout instead makes this a real package (an
`__init__.py` present), `import _core` still works because Python resolves
an unqualified top-level import against `sys.path`, and the package's own
directory is on it once installed — no code change needed either way.

FastAPI/Starlette only (`starlette`) — no third-party dependency beyond the
project's own FastAPI install.
"""

from __future__ import annotations

import _core
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware (not BaseHTTPMiddleware — avoids buffering the
    whole response body just to add a few headers) that sets
    `policy.build_headers()` on every HTTP response, overwriting any
    same-named header a downstream handler or another middleware already
    set. This component is the sole authority on these headers within a
    FastAPI app: Starlette/FastAPI set none of them natively, so there is no
    double-set to defer to (contrast the Django adapter, which does have to
    negotiate with `django.middleware.security.SecurityMiddleware` — see
    that file's docstring and the component README's "Headers interplay"
    section)."""

    def __init__(self, app: ASGIApp, *, policy: _core.SecurityHeadersPolicy = _core.DEFAULT_POLICY) -> None:
        self.app = app
        self.policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = scope.get("scheme") == "https"
        headers_to_set = self.policy.build_headers(is_https=is_https)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                names_to_replace = {name.lower().encode() for name in headers_to_set}
                raw_headers = [
                    (name, value) for name, value in raw_headers if name.lower() not in names_to_replace
                ]
                raw_headers.extend(
                    (name.encode(), value.encode()) for name, value in headers_to_set.items()
                )
                message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


def add_security_headers(
    app: Starlette, *, policy: _core.SecurityHeadersPolicy = _core.DEFAULT_POLICY
) -> None:
    """Convenience wiring: `add_security_headers(app)` in place of the
    two-line `app.add_middleware(SecurityHeadersMiddleware, policy=...)` a
    caller would otherwise write by hand."""
    app.add_middleware(SecurityHeadersMiddleware, policy=policy)


async def security_headers_dependency(request: Request, response: Response) -> None:
    """A per-route alternative to the middleware, for the rare case a
    project wants headers on one router/route rather than the whole app
    (e.g. a docs route deliberately relaxed). Most apps should use
    `add_security_headers()` instead — secure-baseline requires headers on
    every response by default, not per-route opt-in."""
    is_https = request.url.scheme == "https"
    for name, value in _core.DEFAULT_POLICY.build_headers(is_https=is_https).items():
        response.headers[name] = value
