<!--
block: components/security/cors-lockdown  # catalog component
needs:
  - starlette (via the project's FastAPI install): fastapi.py wires Starlette's own CORSMiddleware from the policy
  - django-cors-headers: the Django convention for CORS; django.py emits its settings dict from the same policy but does not import the package itself (declared here, not a hard import)
exposes:
  - CORSPolicy, InsecureCORSPolicyError -- the framework-neutral explicit-allowlist policy in _core.py
  - fastapi.py: add_cors(app, policy)
  - django.py: cors_settings(policy) -> dict, CORS_MIDDLEWARE_CLASSPATH, REQUIRED_INSTALLED_APP
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# cors-lockdown

Full composition-contract detail (exact NEEDS/EXPOSES prose) lives in the
"Composition contract" section below — this header is kept short so the
plugin's freshness-header lint (which only scans a file's first 1000 bytes)
reliably finds `last-verified` on every README, regardless of header length.

A dual-framework middleware component: an explicit-allowlist CORS policy
object in `_core.py` that refuses to construct an insecure configuration,
thin wiring of Starlette's own `CORSMiddleware` in `fastapi.py`, and a
config emitter for `django-cors-headers`' settings in `django.py`. Embodies
`references/security/secure-baseline.md`'s "CORS lockdown" section exactly.
Lives at `templates/components/security/cors-lockdown/` in this repo; Stage
3-4 backend blocks copy the whole directory into
`app/core/security/cors_lockdown/`.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- The policy: explicit allowlist, no wildcard, ever
- FastAPI: thin wiring over Starlette's own middleware
- Django: an emitter, not a middleware
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Starlette** (via the project's FastAPI install) — `fastapi.py` does not
  reimplement CORS handling; it validates a policy and hands the translated
  kwargs straight to Starlette's own `CORSMiddleware`.
- **`django-cors-headers`** — the Django-ecosystem convention for CORS.
  `django.py` emits that package's settings dict from the same
  `CORSPolicy`, but never imports the package itself — a project adds it
  (`uv add django-cors-headers` / `pip install django-cors-headers`) and
  puts `"corsheaders"` in `INSTALLED_APPS` itself; this component only
  guarantees the settings values are correct and derived from one source of
  truth.

**EXPOSES**
- `CORSPolicy` (frozen dataclass, validated at construction),
  `InsecureCORSPolicyError` — in `_core.py`.
- `fastapi.py`: `add_cors(app, policy)`.
- `django.py`: `cors_settings(policy) -> dict` (the settings translation),
  `CORS_MIDDLEWARE_CLASSPATH` and `REQUIRED_INSTALLED_APP` (the exact
  strings a project's `MIDDLEWARE`/`INSTALLED_APPS` needs, so a project
  doesn't have to hand-type `django-cors-headers`' own dotted path).
- Its co-located doc fragment: `docs/fragment.md`.

## The policy: explicit allowlist, no wildcard, ever

`CORSPolicy(allow_origins=...)` — `allow_origins` is **required** and must
be non-empty; there is no default that means "any origin". Construction
raises `InsecureCORSPolicyError` if:
- `allow_origins` is empty, or
- `allow_origins` contains a bare `"*"` — **with or without**
  `allow_credentials` (see "Judgment calls" for why this component is
  stricter than the baseline's literal "never wildcard with credentials"
  rule), or
- any origin entry is blank — **unconditionally, not only when
  `allow_credentials=True`** (a blank entry can never match a real
  `Origin` header regardless of the credentials setting, so it's rejected
  the same way either way).

Defaults beyond the required origins list are minimal: `allow_methods=("GET",
"HEAD", "POST")`, `allow_headers=("Content-Type", "Authorization")`,
`max_age=600`, `allow_credentials=False`. Build a distinct `CORSPolicy` per
environment (dev/staging/prod) with that environment's actual origin(s) —
never one shared list imported across all three, per the baseline.

## FastAPI: thin wiring over Starlette's own middleware

`add_cors(app, policy)` is exactly:
```python
app.add_middleware(CORSMiddleware, **policy.to_starlette_kwargs())
```
`to_starlette_kwargs()` maps 1:1 onto Starlette's `CORSMiddleware.__init__`
parameters — this component adds no CORS logic Starlette doesn't already
have; it adds construction-time validation Starlette's own middleware
doesn't enforce (Starlette will happily accept `allow_origins=["*"]` with
`allow_credentials=True` and produce a broken/insecure preflight response;
this component's `CORSPolicy` never lets that configuration exist).

## Django: an emitter, not a middleware

`django.py` contains no Django import beyond typing and produces no request-
handling code at all — `django-cors-headers`' own `CorsMiddleware` already
does that well; reimplementing it here would mean maintaining a second CORS
implementation that could drift from the first. `cors_settings(policy)`
returns the settings dict; merge it into `settings.py`:
```python
from app.core.security.cors_lockdown._core import CORSPolicy
from app.core.security.cors_lockdown.django import cors_settings

globals().update(cors_settings(CORSPolicy(allow_origins=["https://app.example.com"])))
```
Add `"corsheaders"` to `INSTALLED_APPS` and
`django_mod.CORS_MIDDLEWARE_CLASSPATH` to `MIDDLEWARE`, placed **as early as
possible and specifically before** `django.middleware.common.CommonMiddleware`
— `django-cors-headers`' own documented requirement, since `CommonMiddleware`
can issue a redirect response that never reaches `CorsMiddleware` for header
injection if placed after it.

## Testing

`tests/test_core.py` covers every `InsecureCORSPolicyError` trigger
(wildcard alone, wildcard with credentials, empty allowlist, a blank
origin entry both with and without credentials, and a whitespace-only
origin entry), the minimal defaults, and both translation functions'
exact output shape. `tests/test_fastapi.py` exercises a real Starlette
`TestClient` against `add_cors()`-wired app: a preflight from an allowed
origin gets the correct `Access-Control-Allow-*`/`Max-Age` headers, a
preflight from a disallowed origin gets no `Access-Control-Allow-Origin`
(the mechanism the browser actually enforces the block on), and a simple
GET from an allowed origin gets the header too. `tests/test_django.py`
covers the settings-emitter's output matching `_core`'s own translation and
the exposed classpath/app-name constants (no request/response test — that
behavior belongs to `django-cors-headers` itself, not this component).

Run:
```
uv run --python 3.13 --with fastapi --with httpx --with pytest --with 'django==5.2.*' -- \
  pytest templates/components/security/cors-lockdown/tests/ -q
```

## Judgment calls

- **Stricter than the baseline's literal minimum: no bare wildcard origin
  at all, not just "no wildcard with credentials".** The baseline
  (`references/security/secure-baseline.md`) states "never `*` combined
  with `credentials: true`", which technically leaves room for
  `allow_origins=["*"], allow_credentials=False` as compliant. This
  component is an **explicit-allowlist** component by name and by design —
  a policy object that still permits "any origin whatsoever" for the
  no-credentials case has quietly defeated the point of being an allowlist.
  A project that genuinely wants a public, unauthenticated, any-origin API
  doesn't need this component's guardrails at all and can wire
  `CORSMiddleware` directly.
- **`django.py` never imports `django-cors-headers`.** Declaring it as a
  NEEDS rather than a hard `import corsheaders` means this file (and this
  component's tests) never require the package installed just to translate
  a policy into its settings shape — the same lazy-dependency posture
  `secrets-loading`'s `boto3` handling uses, applied to a settings-only
  integration instead of a runtime client.
- **`to_django_cors_headers_settings()` lowercases header names.**
  `django-cors-headers`' `CORS_ALLOW_HEADERS` is documented and
  conventionally written in lowercase (`"content-type"`, not
  `"Content-Type"`) even though HTTP headers are technically case-
  insensitive — lowercasing at the translation boundary means a
  `CORSPolicy` author can still write headers in the conventional
  `Content-Type` casing without producing a settings value that looks
  inconsistent with the rest of a Django project's `settings.py`.
