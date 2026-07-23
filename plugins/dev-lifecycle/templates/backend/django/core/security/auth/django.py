# Vendored from templates/components/security/auth (django.py); keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: `import _core` and `import _cookies` (bare sibling imports) rewritten to
# `from . import _core` / `from . import _cookies` (package-relative) for in-app
# packaging — see this block's README.md "Vendored components" invariant. The
# source docstring's own "copy this whole directory" line already lists only
# `_core.py`/`_cookies.py` alongside this file (this component's `fastapi.py` was
# never part of what django.py itself says to vendor), so no file-list edit was
# needed here. The rest of this file is unchanged: every other reference stays
# `_core.<name>` / `_cookies.<name>`.

"""Django wiring for the auth component: `resolve_principal(request,
auth_service)` -- an async helper resolving a request's `Authorization`
header into `_core.AccessClaims` -- `require_roles(request, auth_service,
*roles)` for role-gated views, the `AUTH_ERROR_HTTP` exception ->
(status, code-string) table an app's own exception handler uses to render
`_core.AuthError` (and this file's `InsufficientRole`) as its
`ErrorEnvelope`, and (Stage 5d, #46) DRF-free glue over `_cookies.py`'s
framework-neutral cookie/CSRF transport -- `set_auth_cookies`,
`clear_auth_cookies`, `read_refresh_cookie`, `enforce_csrf` -- for a
project that authenticates the cookie-based (rather than bearer-token)
way. Canon: references/security/secure-baseline.md ("Tokens (JWT/session)
validated fully").

Drop-in: copy this whole directory (this file, `_core.py`, `_cookies.py`)
into app/core/security/auth/ (add an `__init__.py` re-exporting the public
surface -- see rate-limiting/django.py's own header note for the identical
pattern, and this app's `app/core/security/rate_limiting/__init__.py` for
how that re-export is shaped). This file imports its core logic with bare
`import _core`/`import _cookies` -- flat, directory-local sibling imports,
same as every other framework adapter in this catalog (see security-headers/
django.py's fuller rationale) -- so this file, `_core.py`, `_cookies.py`,
and the `__init__.py` a project adds must be vendored together, never this
file alone.

Django only (`django`) -- deliberately **no `core.*`/project import
anywhere in this file**, matching `_core.py`'s own "no FastAPI/Django/
SQLAlchemy import" posture in reverse, and matching `fastapi.py`'s
identical "no `app.*` import" rule for this component's other adapter:
this file is pure framework glue over the framework-neutral core, with
zero knowledge of any particular project's settings, models, or DB
session/ORM. `auth_service` (an `_core.AuthService`) is supplied BY the
caller on every call below -- this file only declares the shape it needs
(an object with an async `resolve_access(token)` method), never imports or
constructs one itself. Deliberately Django-only, not DRF-specific --
`request.headers` (a case-insensitive mapping) is present on both a plain
`django.http.HttpRequest` and DRF's `rest_framework.request.Request`
(which subclasses it), so a project without Django REST Framework can use
this adapter too; no `rest_framework` import appears anywhere in this
file.

**No dependency-injection factory here, unlike `fastapi.py`.** FastAPI's
`Depends()` system is why that adapter's `build_get_current_principal`
returns a *dependency* (a callable FastAPI itself calls per-request) and
`require_roles` composes dependencies together. Django/DRF views have no
equivalent auto-invoked injection point, so this adapter's two functions
are plain `async def` helpers a view calls directly and awaits itself --
`claims = await resolve_principal(request, auth_service)` (or
`await require_roles(request, auth_service, "admin")` when the route also
needs a role check) -- rather than something wired declaratively onto the
view/route the way `Depends(get_current_principal)` is.

**Error mapping lives here, not in `_core.py`, deliberately** -- see
`_core.py`'s own module docstring ("this module raises its OWN exception
hierarchy... each exception's docstring names the `ErrorCode` member... a
framework adapter's exception handler is expected to map it onto").
`AUTH_ERROR_HTTP` is that mapping for Django, keyed by exception type,
valued `(status_code, code_string)` -- STRING code names
(`"unauthenticated"`, `"conflict"`, `"permission_denied"`), not the
app-layer `ErrorCode` enum itself, so this file needs no
`core.contract.errors`/`app.core.errors`-style import (which would
violate the "no project import" rule above): the app's own exception
handler looks up the raised exception's type in this table and constructs
its OWN `ErrorCode` member from the string, e.g.
`ErrorCode(AUTH_ERROR_HTTP[type(exc)][1])` -- the identical shape
`fastapi.py`'s own `AUTH_ERROR_HTTP` table uses, so an app that tracks
both adapters (or migrates between them) reuses one mapping-table shape
either way.

**Cookie/CSRF glue (Stage 5d, #46) is DRF-free too.** `set_auth_cookies`/
`clear_auth_cookies` below both call `response.set_cookie(...)` --
`clear_auth_cookies` via `_cookies.py`'s `clear_*_cookie_kwargs()`
(`max_age=0`, which expires the cookie immediately; see that module's own
docstring on why `Max-Age=0` is used rather than a separate
`delete_cookie` call) -- present on both a plain `django.http.HttpResponse`
and DRF's `rest_framework.response.Response` (which subclasses it), so
`response` is typed generically here and this file constructs/imports
neither. `read_refresh_cookie`/`enforce_csrf` read `request.COOKIES`/
`request.headers`, both present on the same plain-Django-vs-DRF request
pair `resolve_principal` already reads `request.headers` from above. No
DRF `permission_class` is defined here -- a Django-BLOCK app's own
`HasRole`-style permission class (composing `require_roles` above) is
application code, not part of this vendored, framework-glue-only file.
"""

from __future__ import annotations

from typing import Any

from . import _core
from . import _cookies


class InsufficientRole(_core.AuthError):
    """Raised by `require_roles()` below when an authenticated principal's
    `AccessClaims.roles` doesn't cover every role the route demands. NOT
    part of `_core.py`'s own exception hierarchy (that module has no
    concept of roles beyond carrying the `roles` claim through) -- this is
    the "dedicated component exception" `AUTH_ERROR_HTTP` maps onto the
    EXISTING `permission_denied` (403) `ErrorCode` member. Deliberately
    does NOT invent a new `ErrorCode`: `error-envelope/errors.py`'s enum is
    LOCKED, and "authenticated but not allowed" is exactly what
    `permission_denied` already means (see that module's
    `PermissionDeniedError` docstring). Identical in shape and mapping to
    `fastapi.py`'s own `InsufficientRole` -- kept as two separate classes
    (one per adapter module) rather than one shared definition because
    each adapter is meant to be vendored and read standalone, matching the
    rest of this component's "no cross-adapter-file import" posture."""


# The exception -> (HTTP status, ErrorCode STRING value) table an app's own
# AppError-family exception handler consults for every exception this
# module (or `_core.py`) can raise. String values, not the `ErrorCode`
# enum itself -- see this file's module docstring for why. `InvalidToken`
# and `TokenReused` map to the SAME (401, "unauthenticated") entry
# deliberately -- see `_core.py`'s `TokenReused` docstring on why a reuse
# event must be indistinguishable from any other invalid-token response at
# the wire. Identical table to `fastapi.py`'s own `AUTH_ERROR_HTTP`.
AUTH_ERROR_HTTP: dict[type[Exception], tuple[int, str]] = {
    _core.InvalidCredentials: (401, "unauthenticated"),
    _core.InvalidToken: (401, "unauthenticated"),
    _core.TokenReused: (401, "unauthenticated"),
    _core.EmailAlreadyExists: (409, "conflict"),
    _core.InvalidSingleUseToken: (401, "unauthenticated"),
    InsufficientRole: (403, "permission_denied"),
    _cookies.CsrfValidationError: (403, "permission_denied"),
}


async def resolve_principal(request: Any, auth_service: Any) -> Any:
    """Resolves `request`'s `Authorization` header into `_core.AccessClaims`
    -- what a Django/DRF view calls (and awaits) to know "who is calling,
    and with which roles" before running its own body.

    `auth_service` is an `_core.AuthService` (or anything duck-typed the
    same way -- only `resolve_access` is called on it) the CALLER
    constructs and passes in on every call, never imported or built here --
    see this module's own docstring on why (no project-level settings/DB
    session exists at this layer to build one from).

    A missing `Authorization` header, or one that isn't the literal
    `Bearer <token>` shape, raises `_core.InvalidToken` DIRECTLY -- the
    SAME exception `AuthService.resolve_access` itself raises for a
    present-but-invalid token, so "no token" and "bad token" are
    indistinguishable at this layer too (an app's exception handler
    renders both as the identical 401 `unauthenticated` envelope via
    `AUTH_ERROR_HTTP`) -- mirroring `fastapi.py`'s
    `build_get_current_principal`'s identical handling of its own
    `auto_error=False` HTTPBearer's `credentials is None` case. Never
    returns `None`/optional -- a caller either gets real `AccessClaims` back
    or this coroutine raises, same contract as `fastapi.py`'s dependency."""
    header = request.headers.get("Authorization")
    if header is None:
        raise _core.InvalidToken("No bearer token was presented.")
    scheme, _, token = header.partition(" ")
    # Scheme compared case-INSENSITIVELY (`scheme.lower()`) per RFC 7235
    # (auth-scheme tokens are case-insensitive), matching Starlette's own
    # `HTTPBearer` (`fastapi.py`'s side) so a client sending `bearer <token>`
    # or `Bearer <token>` is accepted identically against BOTH backends --
    # the token VALUE itself stays case-sensitive.
    if scheme.lower() != "bearer" or not token:
        raise _core.InvalidToken("No bearer token was presented.")
    return await auth_service.resolve_access(token)


async def require_roles(request: Any, auth_service: Any, *roles: str) -> Any:
    """Resolves `request`'s principal (via `resolve_principal` above) and
    additionally enforces that the resolved principal's `roles` cover
    every role listed in `*roles`, raising `InsufficientRole` (-> 403
    `permission_denied`, see `AUTH_ERROR_HTTP`) otherwise. Returns the
    resolved `AccessClaims` on success, so a view can use its result
    directly:

        claims = await require_roles(request, auth_service, "admin")

    Membership is checked with `set(roles) <= set(claims.roles)` -- EVERY
    listed role must be present (AND semantics), not merely one of them;
    a route needing OR semantics composes multiple single-role calls with
    its own logic instead, since "any one of several roles suffices" is a
    route-specific policy this generic helper does not guess at. Identical
    membership-check semantics to `fastapi.py`'s `require_roles` -- the
    difference is purely mechanical (an awaited helper here, a composed
    `Depends()` dependency there), not a difference in what "sufficient
    role" means."""
    claims = await resolve_principal(request, auth_service)
    required = set(roles)
    if not required.issubset(set(claims.roles)):
        raise InsufficientRole("This action requires a role the current principal does not have.")
    return claims


# ---------------------------------------------------------------------------
# Cookie/CSRF transport glue (DRF-free thin wrapper over `_cookies.py`)
# ---------------------------------------------------------------------------
#
# Everything below is THIN glue: all cookie-flag/CSRF-check logic itself
# lives in the framework-neutral `_cookies.py`, imported above. These
# functions exist only to map `_cookies.py`'s framework-neutral dicts and
# plain-string reads onto a generic Django request/response pair -- they
# are called by a project's own `/auth/login`, `/auth/refresh`, and
# `/auth/logout` views (a later agent's job -- see this component's
# README's "Cookie/CSRF transport" section), never by anything in this
# file itself. `request`/`response` are typed generically (`Any`) rather
# than as `django.http.HttpRequest`/`HttpResponse` because a DRF
# `rest_framework.request.Request`/`Response` pair works identically here
# -- both subclass the plain-Django pair and expose the same
# `.COOKIES`/`.headers`/`.set_cookie(...)` surface this glue reads/calls.


def set_auth_cookies(response: Any, *, refresh_value: str, csrf_value: str, max_age: int) -> None:
    """Sets BOTH the refresh-token and CSRF-token cookies on `response` --
    called after a successful login or refresh, once the caller has a new
    `refresh_value` (the raw refresh JWT `_core.TokenService.mint_refresh`/
    `AuthService.refresh` just minted) and a new `csrf_value` (from
    `_cookies.generate_csrf_token()`). `max_age` is shared by both cookies
    and passed straight through to `_cookies.build_refresh_cookie_kwargs`/
    `build_csrf_cookie_kwargs` -- typically the refresh token's own TTL in
    seconds, so neither cookie outlives the token it's paired with.
    Identical behavior to `fastapi.py`'s own `set_auth_cookies` -- the
    difference is purely mechanical (`response.set_cookie` is a plain
    Django/DRF method call here, a Starlette `Response` method there)."""
    response.set_cookie(**_cookies.build_refresh_cookie_kwargs(refresh_value, max_age))
    response.set_cookie(**_cookies.build_csrf_cookie_kwargs(csrf_value, max_age))


def clear_auth_cookies(response: Any) -> None:
    """Clears BOTH the refresh-token and CSRF-token cookies on `response`
    -- called on logout, via `_cookies.clear_refresh_cookie_kwargs`/
    `clear_csrf_cookie_kwargs` (each `max_age=0`, expiring the cookie
    immediately)."""
    response.set_cookie(**_cookies.clear_refresh_cookie_kwargs())
    response.set_cookie(**_cookies.clear_csrf_cookie_kwargs())


def read_refresh_cookie(request: Any) -> str | None:
    """Reads the raw refresh-token cookie off `request.COOKIES` (a plain
    dict-like mapping present on both `django.http.HttpRequest` and DRF's
    `rest_framework.request.Request`) -- `None` if it was never set or
    has already been cleared. The caller (a `/auth/refresh` or
    `/auth/logout` view) is responsible for deciding what a missing
    cookie means (typically raising `_core.InvalidToken` itself, the same
    exception `AuthService.refresh`/`resolve_access` raise for any other
    invalid-token case -- this function does not raise on a missing
    cookie itself, it only reads)."""
    return request.COOKIES.get(_cookies.REFRESH_COOKIE_NAME)


def enforce_csrf(request: Any) -> None:
    """Reads the `csrf_token` cookie (`request.COOKIES`) and the
    `X-CSRF-Token` header (`request.headers`) off `request` and runs
    `_cookies.verify_double_submit` against them -- raises
    `_cookies.CsrfValidationError` (-> 403 `permission_denied`, see
    `AUTH_ERROR_HTTP` above) on any double-submit failure. Called by a
    cookie-authenticated view BEFORE acting on the request body -- never
    on the bearer-token path (`resolve_principal`/`require_roles` above),
    which has no CSRF exposure to begin with; see `_cookies.py`'s own
    module docstring for why the two paths are treated differently."""
    _cookies.verify_double_submit(
        csrf_cookie=request.COOKIES.get(_cookies.CSRF_COOKIE_NAME),
        csrf_header=request.headers.get("X-CSRF-Token"),
    )
