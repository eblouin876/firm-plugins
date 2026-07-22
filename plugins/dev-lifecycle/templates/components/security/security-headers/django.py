"""Django wiring for the security-headers component: a MIDDLEWARE class that
sets the header set `_core.SecurityHeadersPolicy` builds on every outbound
response, taking the final word over any overlapping header Django's own
`django.middleware.security.SecurityMiddleware` may already have set. Canon:
references/security/secure-baseline.md ("Security headers & CSP").

Drop-in: copy this whole directory (this file, `_core.py`, `fastapi.py`)
into app/core/security/security_headers/ and keep them together. This file
imports its core logic with a bare `import _core`, matching `fastapi.py` —
see that file's docstring for why a bare (not relative) import is correct
here.

Django only (`django`) — no third-party dependency.

--- Headers interplay with Django's own SecurityMiddleware (judgment call) ---
Django 5.2's `SecurityMiddleware` already sets some of this same header set
natively, gated by settings: `X-Content-Type-Options: nosniff` (if
`SECURE_CONTENT_TYPE_NOSNIFF`, default True), `Strict-Transport-Security`
(if `SECURE_HSTS_SECONDS > 0`, default 0/off), and `Referrer-Policy` (if
`SECURE_REFERRER_POLICY`, default `"same-origin"`). Two middlewares racing
to set the same header with different values is worse than either alone —
whichever runs LAST in the response phase silently wins with no signal that
the other's value was discarded.

This component's middleware is declared authoritative: it force-overwrites
these headers regardless of what ran before it. To avoid the two disagreeing
in the first place (not just "the right one wins by accident of ordering"),
a project adopting this component should set in `settings.py`:

    SECURE_CONTENT_TYPE_NOSNIFF = False   # this middleware sets it instead
    SECURE_HSTS_SECONDS = 0               # this middleware sets it instead
    SECURE_REFERRER_POLICY = None         # this middleware sets it instead

and place `SecurityHeadersMiddleware` BEFORE
`"django.middleware.security.SecurityMiddleware"` in `MIDDLEWARE` — Django
runs `process_response` bottom-to-top (reverse of the list), so the
middleware listed EARLIER gets the final word on the outbound response.
Listing ours earlier than SecurityMiddleware means ours runs last and its
values are what the client actually receives, matching "component wins"
even if a project forgets to flip the settings above.

`X-Frame-Options` is set by Django's own
`django.middleware.clickjacking.XFrameOptionsMiddleware`
(`SECURE_FRAME_DENY`... actually `X_FRAME_OPTIONS`, default `"DENY"`) — same
posture as this component's default, and this middleware overwrites it too
for consistency regardless. `Content-Security-Policy` and
`Permissions-Policy` have no Django-native equivalent in 5.2, so there is no
interplay to manage for those two.

--- Deployment note: HSTS behind a TLS-terminating proxy (MEDIUM-6) ---
`is_https` (below) comes from `request.is_secure()`, which Django computes
from `request.META["wsgi.url_scheme"]` UNLESS `SECURE_PROXY_SSL_HEADER` is
set in `settings.py`. Behind a TLS-terminating proxy/load balancer (ALB,
nginx, Caddy terminating TLS and forwarding plain HTTP to the app -- the
common production shape), Django's own WSGI server sees a plain-HTTP
connection even though the original client used HTTPS:
`request.is_secure()` returns `False`, and `Strict-Transport-Security` is
SILENTLY never sent, no error anywhere. This is a missing prerequisite, not
a bug in this middleware: set
`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` in
`settings.py` so Django trusts the proxy's `X-Forwarded-Proto` header --
and ONLY do this once the proxy is confirmed to strip/overwrite any
client-supplied `X-Forwarded-Proto` before forwarding (the same
proxy-trust caveat rate-limiting's `client_ip_key` documents for
`X-Forwarded-For`; an untrusted, client-controlled `X-Forwarded-Proto`
would let a client spoof "I'm on HTTPS" over a genuinely plaintext
connection). Verify by confirming `Strict-Transport-Security` is present
on a real deployed response behind the actual proxy, not just in local dev
where the app IS the TLS terminator.
"""

from __future__ import annotations

from typing import Callable

import _core
from django.http import HttpRequest, HttpResponse


class SecurityHeadersMiddleware:
    """New-style Django middleware (the `__init__(get_response)` /
    `__call__(request)` form, current since Django 1.10). Force-overwrites
    the header set on every response — see this file's module docstring for
    the placement/settings this depends on to avoid disagreeing with
    Django's own SecurityMiddleware."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
        *,
        policy: _core.SecurityHeadersPolicy = _core.DEFAULT_POLICY,
    ) -> None:
        self.get_response = get_response
        self.policy = policy

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        for name, value in self.policy.build_headers(is_https=request.is_secure()).items():
            response[name] = value
        return response
