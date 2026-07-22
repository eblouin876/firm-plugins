<!--
block: components/security/security-headers  # catalog component
needs:
  - starlette (via the project's FastAPI install): fastapi.py's SecurityHeadersMiddleware is pure ASGI, imported nowhere but from a FastAPI/Starlette app
  - django (5.2.x): django.py's SecurityHeadersMiddleware is a standard MIDDLEWARE class
  - settings coordination (Django only): disable SECURE_CONTENT_TYPE_NOSNIFF/SECURE_HSTS_SECONDS/SECURE_REFERRER_POLICY and place this middleware before SecurityMiddleware -- see django.py's module docstring
exposes:
  - SecurityHeadersPolicy, DEFAULT_POLICY, CSPPolicy -- the framework-neutral policy/builder in _core.py
  - fastapi.py: SecurityHeadersMiddleware, add_security_headers(app, *, policy=...), security_headers_dependency (per-route escape hatch)
  - django.py: SecurityHeadersMiddleware
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# security-headers

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: framework-neutral header-building
logic in `_core.py`, a pure-ASGI middleware in `fastapi.py`, and a Django
`MIDDLEWARE` class in `django.py`. Sets `Strict-Transport-Security`,
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`, and `Content-Security-Policy` on every HTTP response by
default — middleware, not per-route opt-in, per
`references/security/secure-baseline.md`'s "Security headers & CSP" section,
which this component embodies exactly. Lives at
`templates/components/security/security-headers/` in this repo; Stage 3-4
backend blocks copy the whole directory into
`app/core/security/security_headers/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- Layout and the import pattern
- The policy
- CSP: strict default, explicit relaxation
- Permissions-Policy: minimal by default
- Headers interplay (judgment call)
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Starlette** (via the project's own FastAPI install) — `fastapi.py`'s
  `SecurityHeadersMiddleware` is pure ASGI (no `BaseHTTPMiddleware`, no
  response-body buffering); it imports only `starlette.*`, never `fastapi`
  itself, so it works unchanged in a bare-Starlette app too.
- **Django 5.2.x** — `django.py`'s `SecurityHeadersMiddleware` is a standard
  new-style `MIDDLEWARE` class.
- **Settings coordination (Django only)** — Django's own
  `SecurityMiddleware`/`XFrameOptionsMiddleware` already set some of this
  same header set; see "Headers interplay" below for the exact settings to
  flip and where in `MIDDLEWARE` to place this component's middleware.

**EXPOSES**
- `SecurityHeadersPolicy` (frozen dataclass), `DEFAULT_POLICY` (its secure
  default instance), `CSPPolicy` (the CSP directive builder) — all in
  `_core.py`.
- `fastapi.py`: `SecurityHeadersMiddleware` (the pure-ASGI class),
  `add_security_headers(app, *, policy=DEFAULT_POLICY)` (one-line wiring),
  `security_headers_dependency` (a per-route escape hatch — see its own
  docstring for why the middleware is the right default and this isn't).
- `django.py`: `SecurityHeadersMiddleware`.
- Its co-located doc fragment: `docs/fragment.md`.

## Layout and the import pattern

Three files, copied together: `_core.py` (framework-neutral), `fastapi.py`,
`django.py`. Both adapter files import their shared logic with a bare
`import _core` — not a relative `from . import _core` — because these files
ship as siblings on the import path rather than assuming a formal package;
see the top-of-file note in `fastapi.py`/`django.py` for the exact
resolution rule. **Deliberately named `fastapi.py` and `django.py`** to name
exactly which framework each wires up — once copied into
`app/core/security/security_headers/`, they're reached as
`app.core.security.security_headers.fastapi` /
`...django`, never as a bare top-level `import fastapi`/`import django`, so
there's no collision with the real installed packages in actual use. (This
repo's own test harness, which never puts this directory on `sys.path`,
works around the collision risk that a naive flat-`sys.path` test setup
would hit — see `tests/conftest.py`'s docstring.)

## The policy

`SecurityHeadersPolicy` (frozen, `dataclasses.replace()` to override a
field) builds the header dict via `.build_headers(is_https=...)`:

| Header | Default | Notes |
| --- | --- | --- |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Only set when `is_https=True` — see "Judgment calls". `preload` is opt-in (`hsts_preload=True`), a one-way door via the browser preload list. |
| `X-Content-Type-Options` | `nosniff` | Fixed; not configurable — there's no legitimate reason to disable MIME-sniffing protection. |
| `X-Frame-Options` | `DENY` | Configurable (`frame_options=`) for a documented exception (e.g. `SAMEORIGIN` for an app that legitimately frames itself). |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | The modern browser default already, set explicitly rather than relying on it. |
| `Permissions-Policy` | camera/microphone/geolocation/browsing-topics/interest-cohort all denied (`feature=()`) | See "Permissions-Policy" below. |
| `Content-Security-Policy` | `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'` | See "CSP" below. |

`is_https` comes from the request itself in both adapters (`scope["scheme"]`
in ASGI, `request.is_secure()` in Django) — not a static config flag — so
the same policy object is correct in a mixed local-dev (`http://localhost`)
+ deployed (`https://`) setup without per-environment branching.

## CSP: strict default, explicit relaxation

`CSPPolicy()` starts at the secure-baseline floor:
`default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors
'none'` — no `unsafe-inline`/`unsafe-eval`, nothing external allowlisted.
Widen it explicitly and only for what's actually needed:

```python
from _core import SecurityHeadersPolicy, CSPPolicy
from dataclasses import replace

policy = replace(
    SecurityHeadersPolicy(),
    csp=CSPPolicy().allow("script-src", "'self'", "https://cdn.example.com")
        .allow("img-src", "'self'", "https://images.example.com"),
)
```

`.allow(directive, *sources)` returns a **new** `CSPPolicy` — the original is
untouched, and calling it is additive to whatever the directive already
allows (it never silently overrides an existing constraint on that
directive). `frame-ancestors 'none'` is set by default alongside
`X-Frame-Options: DENY` — belt-and-suspenders, since `frame-ancestors` is the
CSP-native equivalent and takes precedence in browsers honoring both.

## Permissions-Policy: minimal by default

Every commonly-abused or tracking-adjacent feature this component ships an
opinion on (`camera`, `microphone`, `geolocation`, `browsing-topics`,
`interest-cohort`) is denied to every origin by default — an explicit empty
allowlist (`feature=()`), not merely omitted. A project that genuinely uses
one widens exactly that feature:
`dataclasses.replace(DEFAULT_POLICY, permissions_policy={"camera": ("self",)})`
(a full replacement dict, not a merge — pass every feature this project
cares about, matching the "explicit allowlist" posture the rest of this
component uses).

## Headers interplay (judgment call)

**Starlette/FastAPI:** neither sets any of these headers natively — no
double-set to manage. This component is the sole authority.

**Django 5.2:** `SecurityMiddleware` and `XFrameOptionsMiddleware` already
set `X-Content-Type-Options`, `Strict-Transport-Security`,
`Referrer-Policy`, and `X-Frame-Options` under their own settings-gated
defaults. **This component's middleware wins**: it force-overwrites every
header it manages regardless of what ran before it, AND the README
recommends flipping the overlapping Django settings off
(`SECURE_CONTENT_TYPE_NOSNIFF = False`, `SECURE_HSTS_SECONDS = 0`,
`SECURE_REFERRER_POLICY = None`) so the two never actually disagree in the
first place — the force-overwrite is a safety net, not the primary
mechanism. Placement matters too: Django runs `process_response`
bottom-to-top (reverse of `MIDDLEWARE`'s order), so list
`SecurityHeadersMiddleware` **before**
`django.middleware.security.SecurityMiddleware` to guarantee it runs last
and gets the final word — see `django.py`'s module docstring for the full
placement rationale.

## Testing

`tests/test_core.py` covers the policy defaults, HSTS gating on
`is_https`/preload opt-in, CSP's strict default and `.allow()`'s additive/
non-mutating/deduplicating behavior, and Permissions-Policy's deny-by-default
+ override shape. `tests/test_fastapi.py` exercises the real ASGI middleware
against a Starlette `TestClient` (headers present, HSTS present only over
`https://`, and — the load-bearing case — the middleware overwriting a
handler's own conflicting header without duplicating it in the raw header
list). `tests/test_django.py` exercises the middleware via
`django.test.RequestFactory` the same way, including overwriting a header a
prior middleware (simulating Django's own `SecurityMiddleware`) already set.

Run:
```
uv run --python 3.13 --with fastapi --with httpx --with pytest --with 'django==5.2.*' -- \
  pytest templates/components/security/security-headers/tests/ -q
```

## Judgment calls

- **HSTS gated on `is_https`, not unconditionally set.** `Strict-Transport-
  Security` on a plaintext HTTP response either does nothing (most browsers
  ignore it over a non-TLS connection) or, worse, is trivially stripped by a
  MITM on that same plaintext connection before it's ever honored — sending
  it is dead weight at best. Local dev over plain `http://localhost` simply
  never receives the header, which is the correct, intended behavior, not a
  gap this component leaves open.
- **Django-side "component wins": force-overwrite AND recommend disabling
  the overlapping native settings, not one or the other alone.** Relying
  only on placement/force-overwrite would still leave Django's
  `SecurityMiddleware` computing (and then discarding) a value on every
  request — wasted work, and a landmine for the next engineer who moves the
  middleware order without re-reading this doc. Relying only on the settings
  change (no force-overwrite) would leave a silent gap if a project's
  `MIDDLEWARE` list is ever reordered later. Both together is the belt-and-
  suspenders choice.
- **`X-Content-Type-Options` and CSP's `object-src`/`base-uri` are not
  exposed as configurable fields.** Every other header has a documented
  override path; these three are treated as non-negotiable defaults for a
  starter-kit component — a project with a genuine reason to loosen them can
  still construct its own `SecurityHeadersPolicy`/`CSPPolicy` by hand rather
  than this component exposing a footgun field for a case that should be
  rare and deliberate enough to not need a one-line override.
