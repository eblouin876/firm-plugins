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
`TokenReused`, `EmailAlreadyExists`) raised by any handler below is left
UNCAUGHT here — `app/main.py`'s `create_app()` registers a handler for the
`AuthError` base class that renders the vendored component's
`AUTH_ERROR_HTTP` mapping as this app's own `ErrorEnvelope`. No handler
below ever constructs an `ErrorEnvelope`/`AppError` itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_service, get_current_principal
from app.core.db import get_db
from app.core.errors import ErrorEnvelope
from app.core.security.auth import AccessClaims, AuthService, InvalidToken
from app.core.security.auth.stores import SqlAlchemyUserStore
from app.schemas.auth import LoginRequest, PrincipalOut, RefreshRequest, RegisterRequest, TokenResponse

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
) -> PrincipalOut:
    """Delegates straight to `AuthService.register` — raises
    `EmailAlreadyExists` (-> 409 `conflict`) for a duplicate normalized
    email, uncaught here (see module docstring)."""
    user = await auth_service.register(payload.email, payload.password)
    return PrincipalOut(id=uuid.UUID(user.id), email=user.email)


@router.post("/login", response_model=TokenResponse, summary="Login", responses=_UNAUTHENTICATED_RESPONSE)
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Delegates to `AuthService.login` — raises `InvalidCredentials`
    (-> 401 `unauthenticated`) identically for an unknown email or a wrong
    password (see that exception's own docstring on the deliberate
    user-enumeration defense), uncaught here."""
    pair = await auth_service.login(payload.email, payload.password)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh token", responses=_UNAUTHENTICATED_RESPONSE)
async def refresh(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Delegates to `AuthService.refresh` — THE rotation-with-reuse-
    detection state machine (see `_core.py`'s own module docstring and
    `AuthService.refresh`'s docstring for the full 6-step state machine).
    Raises `InvalidToken` or `TokenReused` (both -> 401 `unauthenticated`,
    deliberately indistinguishable at the wire — see `TokenReused`'s own
    docstring), uncaught here. A `TokenReused` raise has, as a side
    effect, ALREADY revoked the token's entire family in the DB by the
    time this handler's caller sees the 401."""
    pair = await auth_service.refresh(payload.refresh_token)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout")
async def logout(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """Delegates to `AuthService.logout` — best-effort and idempotent by
    design (see that method's own docstring): an already-invalid, unknown,
    or already-revoked refresh token still returns 204, never an error.
    Revokes the entire token family, not just the presented token."""
    await auth_service.logout(payload.refresh_token)


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
