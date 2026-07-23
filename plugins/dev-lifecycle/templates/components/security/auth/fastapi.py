"""FastAPI wiring for the auth component: the `HTTPBearer` scheme, a
`build_get_current_principal(get_auth_service)` dependency FACTORY that
resolves the bearer token into `_core.AccessClaims`, a `require_roles(...)`
dependency factory for role-gated routes, the `AUTH_ERROR_HTTP`
exception -> (status, code-string) table an app's own exception handler
uses to render `_core.AuthError` (and this file's `InsufficientRole`) as
its `ErrorEnvelope`, and (Stage 5d, #46) thin Starlette glue over
`_cookies.py`'s framework-neutral cookie/CSRF transport — `set_auth_cookies`,
`clear_auth_cookies`, `read_refresh_cookie`, `enforce_csrf` — for a project
that authenticates the cookie-based (rather than bearer-token) way. Canon:
references/security/secure-baseline.md ("Tokens (JWT/session) validated
fully").

Drop-in: copy this whole directory (this file, `_core.py`, `_cookies.py`)
into app/core/security/auth/ (add an `__init__.py` re-exporting the public
surface — see rate-limiting/fastapi.py's own header note for the identical
pattern, and this app's `app/core/security/rate_limiting/__init__.py` for
how that re-export is shaped). This file imports its core logic with bare
`import _core`/`import _cookies` — flat, directory-local sibling imports,
same as every other framework adapter in this catalog (see security-headers/
fastapi.py's fuller rationale) — so this file, `_core.py`, `_cookies.py`,
and the `__init__.py` a project adds must be vendored together, never this
file alone.

Starlette/FastAPI only (`starlette`, `fastapi`) — deliberately **no
`app.*` import anywhere in this file**, matching `_core.py`'s own "no
FastAPI/Django/SQLAlchemy import" posture in reverse: this file is pure
framework glue over the framework-neutral core, with zero knowledge of any
particular app's settings, models, or DB session. `get_auth_service` (the
factory parameter below) is supplied BY the app — this file only declares
the shape it needs (a zero/kwarg-only-args async callable usable as a
FastAPI dependency that returns an `_core.AuthService`), never imports or
constructs one itself.

**Error mapping lives here, not in `_core.py`, deliberately** — see
`_core.py`'s own module docstring ("this module raises its OWN exception
hierarchy... each exception's docstring names the `ErrorCode` member... a
framework adapter's exception handler is expected to map it onto").
`AUTH_ERROR_HTTP` is that mapping for FastAPI, keyed by exception type,
valued `(status_code, code_string)` — STRING code names
(`"unauthenticated"`, `"conflict"`, `"permission_denied"`), not the
app-layer `ErrorCode` enum itself, so this file needs no
`app.core.errors` import (which would violate the "no `app.*` import"
rule above): the app's own exception handler looks up the raised
exception's type in this table and constructs its OWN `ErrorCode` member
from the string, e.g. `ErrorCode(AUTH_ERROR_HTTP[type(exc)][1])`.
"""

from __future__ import annotations

from typing import Any, Callable

import _core
import _cookies
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# `auto_error=False`: a missing/malformed `Authorization` header should
# reach `build_get_current_principal`'s own dependency body (which raises
# the core `_core.InvalidToken` below) rather than HTTPBearer's own default
# 403 — keeping ONE failure mode (401 `unauthenticated`, via
# `AUTH_ERROR_HTTP`) for "no/bad bearer token", not two different shapes
# depending on whether a header was even sent. Mirrors app/api/deps.py's
# stub-era `bearer_scheme` in the FastAPI block this vendors into.
bearer_scheme = HTTPBearer(auto_error=False)


class InsufficientRole(_core.AuthError):
    """Raised by `require_roles()` below when an authenticated principal's
    `AccessClaims.roles` doesn't cover every role the route demands. NOT
    part of `_core.py`'s own exception hierarchy (that module has no
    concept of roles beyond carrying the `roles` claim through) — this is
    the "dedicated component exception" `AUTH_ERROR_HTTP` maps onto the
    EXISTING `permission_denied` (403) `ErrorCode` member. Deliberately
    does NOT invent a new `ErrorCode`: `error-envelope/errors.py`'s enum is
    LOCKED, and "authenticated but not allowed" is exactly what
    `permission_denied` already means (see that module's
    `PermissionDeniedError` docstring)."""


# The exception -> (HTTP status, ErrorCode STRING value) table an app's own
# AppError-family exception handler consults for every exception this
# module (or `_core.py`) can raise. String values, not the `ErrorCode`
# enum itself — see this file's module docstring for why. `InvalidToken`
# and `TokenReused` map to the SAME (401, "unauthenticated") entry
# deliberately — see `_core.py`'s `TokenReused` docstring on why a reuse
# event must be indistinguishable from any other invalid-token response at
# the wire.
AUTH_ERROR_HTTP: dict[type[Exception], tuple[int, str]] = {
    _core.InvalidCredentials: (401, "unauthenticated"),
    _core.InvalidToken: (401, "unauthenticated"),
    _core.TokenReused: (401, "unauthenticated"),
    _core.EmailAlreadyExists: (409, "conflict"),
    _core.InvalidSingleUseToken: (401, "unauthenticated"),
    InsufficientRole: (403, "permission_denied"),
    _cookies.CsrfValidationError: (403, "permission_denied"),
}


def build_get_current_principal(
    get_auth_service: Callable[..., Any],
) -> Callable[..., Any]:
    """Returns a FastAPI dependency that resolves the request's bearer
    token into `_core.AccessClaims` — what a route depends on to know
    "who is calling, and with which roles" (`Depends(get_current_principal)`
    in a project's own `app/api/deps.py`).

    `get_auth_service` is itself a FastAPI-dependency-shaped callable
    (typically `Depends`-wrapped by the returned dependency below, i.e.
    the app's own per-request `AuthService` provider — bound to that
    request's DB session, see the app-level wiring this component's
    README documents) that returns an `_core.AuthService`. Passed in
    rather than imported: this file has no DB session, no settings, and no
    way to construct an `AuthService` itself (see this module's own
    docstring on the "no `app.*` import" rule) — only the app that vendors
    this file can build one.

    A missing/malformed `Authorization` header (`credentials is None`, from
    `bearer_scheme`'s `auto_error=False`) raises `_core.InvalidToken`
    directly — the SAME exception `AuthService.resolve_access` itself
    raises for a present-but-invalid token, so "no token" and "bad token"
    are indistinguishable at this layer too (an app's exception handler
    renders both as the identical 401 `unauthenticated` envelope via
    `AUTH_ERROR_HTTP`). Never returns `None`/optional — a route depending
    on this dependency either gets real `AccessClaims` or the request never
    reaches the route body at all."""

    async def get_current_principal(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        auth_service: Any = Depends(get_auth_service),
    ) -> Any:
        if credentials is None:
            raise _core.InvalidToken("No bearer token was presented.")
        return await auth_service.resolve_access(credentials.credentials)

    return get_current_principal


def require_roles(
    get_current_principal: Callable[..., Any],
    *roles: str,
) -> Callable[..., Any]:
    """Returns a FastAPI dependency that depends on `get_current_principal`
    (the dependency `build_get_current_principal` returned — passed in
    rather than closed over a module-level name, since this component has
    no fixed one: each project builds its own via `build_get_current_principal`,
    bound to its own `get_auth_service`) and additionally enforces that the
    resolved principal's `roles` cover every role listed in `*roles`,
    raising `InsufficientRole` (-> 403 `permission_denied`, see
    `AUTH_ERROR_HTTP`) otherwise. Use per-route:

        require_admin = require_roles(get_current_principal, "admin")

        @router.delete("/widgets/{id}", dependencies=[Depends(require_admin)])
        ...

    Membership is checked with `set(roles) <= set(claims.roles)` — EVERY
    listed role must be present (AND semantics), not merely one of them;
    a route needing OR semantics composes multiple single-role dependencies
    with its own logic instead, since "any one of several roles suffices"
    is a route-specific policy this generic helper does not guess at."""

    required = set(roles)

    async def dependency(claims: Any = Depends(get_current_principal)) -> Any:
        if not required.issubset(set(claims.roles)):
            raise InsufficientRole("This action requires a role the current principal does not have.")
        return claims

    return dependency


# ---------------------------------------------------------------------------
# Cookie/CSRF transport glue (thin Starlette wrapper over `_cookies.py`)
# ---------------------------------------------------------------------------
#
# Everything below is THIN glue: all cookie-flag/CSRF-check logic itself
# lives in the framework-neutral `_cookies.py`, imported above. These
# functions exist only to map `_cookies.py`'s framework-neutral dicts and
# plain-string reads onto Starlette's own `Response`/`Request` surface —
# they are called by a project's own `/auth/login`, `/auth/refresh`, and
# `/auth/logout` route handlers (a later agent's job — see this
# component's README's "Cookie/CSRF transport" section), never by
# anything in this file itself.


def set_auth_cookies(response: Any, *, refresh_value: str, csrf_value: str, max_age: int) -> None:
    """Sets BOTH the refresh-token and CSRF-token cookies on `response`
    (a Starlette/FastAPI `Response`, or anything exposing the same
    `set_cookie(**kwargs)` method) — called after a successful login or
    refresh, once the caller has a new `refresh_value` (the raw refresh
    JWT `_core.TokenService.mint_refresh`/`AuthService.refresh` just
    minted) and a new `csrf_value` (from `_cookies.generate_csrf_token()`).
    `max_age` is shared by both cookies and passed straight through to
    `_cookies.build_refresh_cookie_kwargs`/`build_csrf_cookie_kwargs` —
    typically the refresh token's own TTL in seconds, so neither cookie
    outlives the token it's paired with."""
    response.set_cookie(**_cookies.build_refresh_cookie_kwargs(refresh_value, max_age))
    response.set_cookie(**_cookies.build_csrf_cookie_kwargs(csrf_value, max_age))


def clear_auth_cookies(response: Any) -> None:
    """Clears BOTH the refresh-token and CSRF-token cookies on `response`
    — called on logout, via `_cookies.clear_refresh_cookie_kwargs`/
    `clear_csrf_cookie_kwargs` (each `max_age=0`, deleting the cookie
    immediately)."""
    response.set_cookie(**_cookies.clear_refresh_cookie_kwargs())
    response.set_cookie(**_cookies.clear_csrf_cookie_kwargs())


def read_refresh_cookie(request: Any) -> str | None:
    """Reads the raw refresh-token cookie off `request.cookies` (a
    Starlette/FastAPI `Request`'s own mapping) — `None` if it was never
    set or has already been cleared. The caller (a `/auth/refresh` or
    `/auth/logout` route handler) is responsible for deciding what a
    missing cookie means (typically raising `_core.InvalidToken` itself,
    the same exception `AuthService.refresh`/`resolve_access` raise for
    any other invalid-token case — this function does not raise on a
    missing cookie itself, it only reads)."""
    return request.cookies.get(_cookies.REFRESH_COOKIE_NAME)


def enforce_csrf(request: Any) -> None:
    """Reads the `csrf_token` cookie and the `X-CSRF-Token` header off
    `request` (a Starlette/FastAPI `Request`) and runs
    `_cookies.verify_double_submit` against them — raises
    `_cookies.CsrfValidationError` (-> 403 `permission_denied`, see
    `AUTH_ERROR_HTTP` above) on any double-submit failure. Called by a
    cookie-authenticated route handler BEFORE acting on the request body —
    never on the bearer-token path (`build_get_current_principal`/
    `require_roles` above), which has no CSRF exposure to begin with; see
    `_cookies.py`'s own module docstring for why the two paths are
    treated differently."""
    _cookies.verify_double_submit(
        csrf_cookie=request.cookies.get(_cookies.CSRF_COOKIE_NAME),
        csrf_header=request.headers.get("X-CSRF-Token"),
    )
