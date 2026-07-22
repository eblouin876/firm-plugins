<!-- fragment: block:components/security/security-headers -->

## Setup
Copy the `security-headers/` directory into
`app/core/security/security_headers/` (keep `_core.py`, `fastapi.py`,
`django.py` together). FastAPI: call `add_security_headers(app)` once at app
construction. Django: add
`"app.core.security.security_headers.django.SecurityHeadersMiddleware"` to
`MIDDLEWARE`, placed **before** `"django.middleware.security.SecurityMiddleware"`,
and set `SECURE_CONTENT_TYPE_NOSNIFF = False`, `SECURE_HSTS_SECONDS = 0`,
`SECURE_REFERRER_POLICY = None` so Django's own middleware stops computing a
value this component overwrites anyway.

## Maintenance
`CSPPolicy().allow(directive, *sources)` is the only sanctioned way to widen
the default CSP — never edit `_core.py`'s `_DEFAULT_CSP_DIRECTIVES` in place.
Review every `.allow()` call site at the same cadence as a dependency
allowlist change: each one is a deliberate trust decision.
