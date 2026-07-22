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
