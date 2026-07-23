"""Auth router (Stage 5a, #41) — real handlers wired against the vendored
`AuthService` (`app/core/security/auth`), replacing the Stage 3 Step 2
stubs (every route used to unconditionally return `HTTPException(501)`;
see `app/api/deps.py`'s pre-Stage-5a history in git log for that stub
era).

Every handler here is thin, matching `app/api/routers/items.py`'s own
"validate, delegate, map, return" shape: no credential/token logic lives
in this file — it's entirely `_core.AuthService`'s job (register/login/
refresh/logout/resolve_access). This router's only real job beyond
delegation is the wire-shape mapping (`_core.UserRecord`/`_core.TokenPair`
-> this app's `PrincipalOut`/`TokenResponse` Pydantic schemas) and — for
`GET /me` only — a second, direct lookup (`SqlAlchemyUserStore.get_by_id`)
to fetch the caller's `email`, since `_core.AccessClaims` (what
`get_current_principal` resolves a bearer token to) intentionally carries
only `sub`/`roles`/`jti`/timestamps, not a full user profile — see that
dataclass's own docstring.

Every `_core.AuthError` subclass (`InvalidCredentials`, `InvalidToken`,
`TokenReused`, `EmailAlreadyExists`, `InvalidSingleUseToken`) raised by any
handler below is left UNCAUGHT here — `app/main.py`'s `create_app()`
registers a handler for the `AuthError` base class that renders the
vendored component's `AUTH_ERROR_HTTP` mapping as this app's own
`ErrorEnvelope`. No handler below ever constructs an `ErrorEnvelope`/
`AppError` itself.

Stage 5c (#45) adds the account-lifecycle surface — `POST /auth/verify-
email`, `POST /auth/request-password-reset`, `POST /auth/reset-password`
— against the vendored `AccountService` (`app/api/deps.py:
get_account_service`), and gives `register` a post-registration side
effect: it now also sends a verification email (`AccountService.
request_email_verification`) and emits an `auth.register` audit event.
`login`'s own behavior (the verification gate, lockout, and its own audit
events) is entirely `AuthService`'s job as of `app/api/deps.py:
get_auth_service`'s Stage 5c wiring — this file's `login` handler itself
is byte-for-byte unchanged from Stage 5a.

Stage 5d (#46) adds WEB COOKIE MODE to `login`/`refresh`/`logout` — an
`X-Auth-Mode: cookie` request header on `POST /auth/login` (default/
anything-else = bearer, the UNCHANGED current behavior) switches the
refresh token from the response BODY to an HttpOnly cookie, paired with a
non-HttpOnly CSRF cookie a SPA echoes back as `X-CSRF-Token` on every
state-changing cookie-authenticated request (double-submit — see the
vendored `_cookies.py`'s own module docstring for the full mechanism).
`refresh`/`logout` are DUAL-SOURCE: `read_refresh_cookie(request)` decides
which path a given request is on, per-request, not per-client-declared
mode — a cookie-bearing browser request takes the cookie path (CSRF
enforced FIRST, before the token is used) and a bearer-only request (no
cookie ever set, e.g. mobile) takes the existing, byte-for-byte-unchanged
bearer path. `X-Auth-Mode` is deliberately read directly off
`request.headers` (not a declared FastAPI `Header(...)` parameter) — see
`login`'s own docstring for why: this keeps it OUT of the exported
OpenAPI schema as a documented parameter, so this stage's contract diff
is exactly the new `/admin/ping` operation (`app/api/routers/admin.py`),
not a parameter addition on an existing one. `enforce_csrf` reads
`X-CSRF-Token` the identical way, for the identical reason."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_account_service, get_auth_service, get_current_principal
from app.core.db import get_db
from app.core.errors import ErrorEnvelope
from app.core.security.auth import (
    AccessClaims,
    AccountService,
    AuthService,
    InvalidToken,
    clear_auth_cookies,
    enforce_csrf,
    generate_csrf_token,
    read_refresh_cookie,
    set_auth_cookies,
)
from app.core.security.auth.stores import AuditAuthEventSink, SqlAlchemyUserStore
from app.schemas.auth import (
    LoginRequest,
    PrincipalOut,
    RefreshRequest,
    RegisterRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# FIX C (whole-PR review, Stage 5a, contract completeness): documents the
# ErrorEnvelope-shaped error responses these routes actually send at
# runtime (via app/main.py's `_auth_error_handler`/`_app_error_handler`),
# same pattern as `app/api/routers/items.py`'s own `_NOT_FOUND_RESPONSE` --
# a `responses={...}` dict of `{status: {"model": ErrorEnvelope,
# "description": ...}}` merged into each route decorator below. Before this
# fix, the exported/frozen OpenAPI contract (`packages/api-client/
# openapi.json`) only documented success + 422 for every /auth/* route --
# the runtime 401/409 responses were entirely undeclared, so a generated
# client had no typed knowledge of them. `POST /auth/logout` is
# deliberately NOT given one of these: it's 204 and idempotent by design
# (see that handler's own docstring) and never raises an error a client
# needs to handle.
_UNAUTHENTICATED_RESPONSE = {
    401: {"model": ErrorEnvelope, "description": "Invalid credentials, or an invalid/expired/revoked token."}
}
_CONFLICT_RESPONSE = {409: {"model": ErrorEnvelope, "description": "An account with this email already exists."}}
# Stage 5c (#45): documents the 401 an invalid/expired/reused single-use
# (verify or reset) token produces -- `_core.InvalidSingleUseToken` maps to
# the SAME (401, "unauthenticated") entry in `AUTH_ERROR_HTTP` every other
# auth failure does (see that exception's own docstring on why "bad token",
# "expired token", and "already-used token" all collapse to one generic,
# wire-indistinguishable response), so this reuses the exact envelope shape
# `_UNAUTHENTICATED_RESPONSE` above already documents, just with wording
# specific to a single-use link rather than a login/refresh credential.
_INVALID_SINGLE_USE_TOKEN_RESPONSE = {
    401: {"model": ErrorEnvelope, "description": "The verify/reset link is invalid, expired, or has already been used."}
}
# Stage 5c (#45): every route in this file with a JSON request body already
# gets FastAPI's native 422 automatically, remapped to this app's
# `ErrorEnvelope` shape by `app/main.py`'s `_install_error_envelope_openapi`
# (applied uniformly across every operation, not per-route) -- this
# constant exists purely so the three new account-lifecycle routes'
# `responses=` declarations are self-documenting about that already-real
# behavior, matching this task's own explicit contract, even though the
# schema content itself is fixed up centrally either way.
_VALIDATION_RESPONSE = {422: {"model": ErrorEnvelope, "description": "Request validation failed."}}


@router.post(
    "/register",
    response_model=PrincipalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register",
    responses=_CONFLICT_RESPONSE,
)
async def register(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    account_service: AccountService = Depends(get_account_service),
) -> PrincipalOut:
    """Delegates straight to `AuthService.register` — raises
    `EmailAlreadyExists` (-> 409 `conflict`) for a duplicate normalized
    email, uncaught here (see module docstring).

    Stage 5c (#45): on success, additionally (a) sends a verification email
    (`AccountService.request_email_verification(user)` — the freshly
    created `UserRecord` `AuthService.register` just returned, so no extra
    lookup is needed) and (b) emits an `auth.register` audit event. Neither
    changes this endpoint's response shape (still 201 `PrincipalOut`) — a
    project whose `Settings.auth_require_email_verification` is `True`
    (the secure default) needs the caller to actually consume the emailed
    link (`POST /auth/verify-email`) before `AuthService.login` will let
    this account in; see that dependency's own docstring.

    Adversarial-review fix (M2): `request_email_verification` is wrapped in
    `try/except Exception` — the user row is already durably committed by
    the time this runs (`AuthService.register` returned successfully), so
    a verification-email failure here (SMTP outage, bounced address) must
    NEVER turn into a 500: the account already exists, a retry would just
    409 on the duplicate email, `require_verification=True` means the
    account can't log in either way, and the wire caller (whoever showed
    the registration form) has no way to "undo" or recover a 500 here —
    it would brick a just-created account with no path forward. Register
    stays 201 regardless of whether the email actually went out; the
    failure is only logged/audited (`auth.register.verification_email_
    failed`, no PII/token in the event), never surfaced to the caller. The
    recovery path for an account whose verification email never arrived is
    `POST /auth/request-password-reset` -> `POST /auth/reset-password` —
    `AccountService.reset_password` now also marks the email verified (see
    `_core.AccountService.reset_password`'s own docstring), so a user who
    never got their verification link can still get into their account."""
    user = await auth_service.register(payload.email, payload.password)
    try:
        await account_service.request_email_verification(user)
    except Exception:
        # M2: never let a verification-email delivery failure 500 an
        # already-committed registration -- see this handler's own
        # docstring above. No PII/token in this event -- just that it
        # happened, for a human to notice and, if needed, resend by hand.
        await AuditAuthEventSink().emit(
            "auth.register.verification_email_failed", actor=user.id, outcome="failure"
        )
    await AuditAuthEventSink().emit("auth.register", actor=user.id, outcome="success")
    return PrincipalOut(id=uuid.UUID(user.id), email=user.email)


@router.post("/login", response_model=TokenResponse, summary="Login", responses=_UNAUTHENTICATED_RESPONSE)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Delegates to `AuthService.login` — raises `InvalidCredentials`
    (-> 401 `unauthenticated`) identically for an unknown email or a wrong
    password (see that exception's own docstring on the deliberate
    user-enumeration defense), uncaught here.

    Stage 5d (#46) web cookie mode: `request.headers.get("X-Auth-Mode")
    == "cookie"` switches this call into cookie mode — read directly off
    `request.headers`, deliberately NOT a declared `Header(...)`
    parameter (see this module's own docstring for why: keeps it out of
    the exported OpenAPI schema as a documented parameter). Anything
    else (absent header, any other value) is BEARER mode — the exact,
    unchanged current behavior; mode is NEVER inferred from User-Agent or
    any other signal, matching the locked design. No CSRF check on login
    either way: login is credential-authenticated (email+password), and
    there is no cookie yet for a CSRF check to protect.

    Cookie mode still returns the SAME `TokenResponse` shape — the wire
    contract (`packages/api-client/openapi.json`'s `TokenResponse`
    schema) is byte-unchanged — but with `refresh_token=""` in the body
    (an empty string still satisfies the schema's required `str` field);
    the real refresh JWT travels ONLY in the HttpOnly `refresh_token`
    cookie `set_auth_cookies` sets below, alongside a fresh, independent
    CSRF cookie (`generate_csrf_token()` — never derived from either
    token) the SPA echoes back as `X-CSRF-Token` on every cookie-
    authenticated `/auth/refresh`/`/auth/logout` call. `max_age` is this
    request's own `jwt_refresh_ttl_seconds`, read off `request.app.state.
    settings` — the SAME `Settings` instance this app was actually
    constructed with (see `app/api/deps.py:get_auth_service`'s own
    docstring on why that's read this way rather than `Depends(
    get_settings)`), so neither cookie outlives the refresh token it's
    paired with."""
    pair = await auth_service.login(payload.email, payload.password)
    if request.headers.get("X-Auth-Mode") == "cookie":
        set_auth_cookies(
            response,
            refresh_value=pair.refresh,
            csrf_value=generate_csrf_token(),
            max_age=request.app.state.settings.jwt_refresh_ttl_seconds,
        )
        return TokenResponse(access_token=pair.access, refresh_token="", token_type="bearer")
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh token", responses=_UNAUTHENTICATED_RESPONSE)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Delegates to `AuthService.refresh` — THE rotation-with-reuse-
    detection state machine (see `_core.py`'s own module docstring and
    `AuthService.refresh`'s docstring for the full 6-step state machine).
    Raises `InvalidToken` or `TokenReused` (both -> 401 `unauthenticated`,
    deliberately indistinguishable at the wire — see `TokenReused`'s own
    docstring), uncaught here. A `TokenReused` raise has, as a side
    effect, ALREADY revoked the token's entire family in the DB by the
    time this handler's caller sees the 401.

    Stage 5d (#46) web cookie mode: DUAL-SOURCE, decided per-request by
    `read_refresh_cookie(request)` (whether the `refresh_token` cookie is
    actually present on THIS request), never by a header the client
    declares — a forged/absent cookie can't claim cookie mode, and a
    genuine cookie-bearing browser request can't accidentally fall onto
    the bearer path either.

    - **Cookie path** (cookie present): `enforce_csrf(request)` runs
      FIRST — raises `CsrfValidationError` (-> 403 `permission_denied`,
      `AUTH_ERROR_HTTP`) before the cookie's refresh token is ever
      presented to `AuthService.refresh` at all, so a request that fails
      the double-submit check never gets to attempt a rotation. The
      request BODY's `payload.refresh_token` is parsed (still required —
      `RefreshRequest`'s schema is unchanged) but its VALUE is
      deliberately ignored; the cookie's own value is what's rotated.
      On success, BOTH cookies are set again — `set_auth_cookies` with
      the NEWLY minted refresh JWT and a FRESH `generate_csrf_token()`
      (never the old CSRF value) — exactly `login`'s own cookie-setting
      shape, so a stolen, already-rotated refresh cookie (reused after
      this response) is rejected the same way `AuthService.refresh`'s
      reuse-detection already rejects any other reused refresh token
      (401, whole family revoked). The response body is `TokenResponse`
      with `refresh_token=""`, matching `login`'s cookie-mode shape.
    - **Bearer path** (no cookie): the exact, unchanged prior behavior —
      `payload.refresh_token` is the real token, no CSRF check, and the
      real new refresh JWT is returned in the body."""
    cookie_refresh_token = read_refresh_cookie(request)
    if cookie_refresh_token is not None:
        enforce_csrf(request)
        pair = await auth_service.refresh(cookie_refresh_token)
        set_auth_cookies(
            response,
            refresh_value=pair.refresh,
            csrf_value=generate_csrf_token(),
            max_age=request.app.state.settings.jwt_refresh_ttl_seconds,
        )
        return TokenResponse(access_token=pair.access, refresh_token="", token_type="bearer")
    pair = await auth_service.refresh(payload.refresh_token)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """Delegates to `AuthService.logout` — best-effort and idempotent by
    design (see that method's own docstring): an already-invalid, unknown,
    or already-revoked refresh token still returns 204, never an error.
    Revokes the entire token family, not just the presented token.

    Stage 5d (#46) web cookie mode: same dual-source shape as `refresh`
    above, decided by `read_refresh_cookie(request)`.

    - **Cookie path** (cookie present): JUDGMENT CALL — logout is
      STATE-CHANGING (it revokes the presented token's entire family via
      `AuthService.logout`), so this endpoint enforces the double-submit
      CSRF check on the cookie path too, `enforce_csrf(request)` called
      BEFORE the best-effort logout runs — a cookie-present request with
      a missing/blank/mismatched `X-CSRF-Token` is rejected 403 at that
      gate and `AuthService.logout` is never even called; it does NOT
      reach 204. This does not weaken `AuthService.logout`'s own
      idempotency for the TOKEN itself — a bad/expired/already-revoked
      cookie value, once past the CSRF gate, still 204s exactly as the
      bearer path already does. On success, clears both cookies
      (`clear_auth_cookies`).
    - **Bearer path** (no cookie): the exact, unchanged prior behavior —
      the body's `refresh_token`, no CSRF check, 204 either way."""
    cookie_refresh_token = read_refresh_cookie(request)
    if cookie_refresh_token is not None:
        enforce_csrf(request)
        await auth_service.logout(cookie_refresh_token)
        clear_auth_cookies(response)
        return None
    await auth_service.logout(payload.refresh_token)
    return None


@router.get("/me", response_model=PrincipalOut, summary="Current principal", responses=_UNAUTHENTICATED_RESPONSE)
async def me(
    claims: AccessClaims = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> PrincipalOut:
    """`get_current_principal` (the vendored component's
    `build_get_current_principal`, bound in `app/api/deps.py`) already
    verified the bearer access token and resolved it to `AccessClaims`
    before this handler body ever runs — a missing/malformed/expired
    token never reaches here at all (see that dependency's own docstring;
    it raises `InvalidToken` -> 401 `unauthenticated` itself).

    `AccessClaims` carries `sub` (the user id) and `roles`, but not
    `email` — this handler does one direct `SqlAlchemyUserStore.get_by_id`
    lookup to fill in `PrincipalOut.email`, independent of `AuthService`
    (which has no "fetch a profile" method — see `_core.py`'s `UserStore`
    Protocol; it's a storage seam for `AuthService`'s own register/login/
    refresh flows, not a general user-lookup API this router reaches for).

    The user having been deleted BETWEEN minting the access token and this
    request (a real, if narrow, race — access tokens are not individually
    revocable, see `Settings.jwt_access_ttl_seconds`'s own docstring) is
    treated as `InvalidToken` (401), matching `AuthService.refresh`'s
    identical "row valid but the user it points to is gone" handling —
    NOT a 404, since the token itself is what's no longer trustworthy, not
    a missing resource the caller asked for by id."""
    user = await SqlAlchemyUserStore(db).get_by_id(claims.sub)
    if user is None:
        raise InvalidToken("This token no longer maps to an active user.")
    return PrincipalOut(id=uuid.UUID(user.id), email=user.email)


# ---------------------------------------------------------------------------
# Account lifecycle (Stage 5c, #45): verify-email / request-password-reset /
# reset-password, against the vendored AccountService.
# ---------------------------------------------------------------------------


@router.post(
    "/verify-email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verify email",
    responses={**_INVALID_SINGLE_USE_TOKEN_RESPONSE, **_VALIDATION_RESPONSE},
)
async def verify_email(
    payload: VerifyEmailRequest,
    account_service: AccountService = Depends(get_account_service),
) -> None:
    """Delegates to `AccountService.verify_email` — raises
    `InvalidSingleUseToken` (-> 401 `unauthenticated`, generic and
    wire-identical to every other single-use-token rejection reason — see
    that exception's own docstring) for an unknown/expired/already-used/
    wrong-purpose token, uncaught here (see module docstring). On success,
    marks the token's owning user's email verified — see `AuthService.
    login`'s `require_verification` gate (`app/api/deps.py:
    get_auth_service`) for why that matters: with `Settings.
    auth_require_email_verification=True` (the default), login for this
    account was refused (generically, as `InvalidCredentials`) until this
    endpoint succeeds."""
    await account_service.verify_email(payload.token)


@router.post(
    "/request-password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset",
    responses=_VALIDATION_RESPONSE,
)
async def request_password_reset(
    payload: RequestPasswordResetRequest,
    account_service: AccountService = Depends(get_account_service),
) -> Response:
    """Delegates to `AccountService.request_password_reset` — that method
    NEVER raises and never reveals whether `payload.email` has an account
    (see its own docstring on the anti-user-enumeration defense this
    mirrors from `AuthService.login`'s own `InvalidCredentials`), so this
    handler ALWAYS returns 202 with a genuinely EMPTY body (`Response(...,
    content=b"")`, not FastAPI's default JSON-encoded `null` a bare
    `return None` with no `response_model` would send instead — a
    byte-identical, content-free response is the strongest form of "this
    endpoint reveals nothing" for a known email and an unknown one alike),
    never a 404/409 that would leak account existence. A `422` (declared
    above) is the one response shape this endpoint CAN still send, for a
    request body that fails `RequestPasswordResetRequest`'s own schema
    validation (e.g. an empty `email` string) before this handler body ever
    runs."""
    await account_service.request_password_reset(payload.email)
    return Response(status_code=status.HTTP_202_ACCEPTED, content=b"")


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset password",
    responses={**_INVALID_SINGLE_USE_TOKEN_RESPONSE, **_VALIDATION_RESPONSE},
)
async def reset_password(
    payload: ResetPasswordRequest,
    account_service: AccountService = Depends(get_account_service),
) -> None:
    """Delegates to `AccountService.reset_password` — raises
    `InvalidSingleUseToken` (-> 401 `unauthenticated`, generic — see
    `verify_email`'s docstring above for the identical rationale) for an
    unknown/expired/already-used/wrong-purpose reset token, uncaught here.
    On success, revokes EVERY refresh-token family the user has (every
    device/session is logged out, not just the one that requested the
    reset — see `AccountService.reset_password`'s own docstring) and, if a
    lockout policy is wired, lifts any failed-login lockout on the
    account — the same shared-session `LockoutPolicy` `app/api/deps.py:
    get_auth_service`'s `AuthService.login` recorded against, so the reset
    account can log in with its new password immediately."""
    await account_service.reset_password(payload.token, payload.new_password)
