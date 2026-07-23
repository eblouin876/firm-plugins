"""Shared FastAPI dependencies. `get_auth_service` is the Stage 5a (#41)
per-request `AuthService` provider — binds this request's DB session
(`get_db`) into fresh `SqlAlchemyUserStore`/`SqlAlchemyRefreshTokenStore`
instances, plus the process-wide `PasswordService` singleton and a
`Settings`-derived `TokenService`, into one `AuthService`. `get_current_
principal` is the vendored auth component's `build_get_current_principal(
get_auth_service)`, bound once at import time — declares the `HTTPBearer`
security scheme in OpenAPI (via the component's `bearer_scheme`) and
resolves a request's bearer token into `_core.AccessClaims` for any route
that depends on it (`app/api/routers/auth.py`'s `GET /auth/me`, and any
future protected route).

Stage 5c (#45) adds `get_account_service` — the per-request `AccountService`
provider `app/api/routers/auth.py`'s new verify-email/request-password-reset/
reset-password routes (and `register`'s post-registration verification-email
side effect) depend on — and wires `get_auth_service` up to the SAME
lockout/verification/audit seams `AccountService` already uses (see
`build_account_service`'s own docstring in `stores.py`): `login` now
consults a real `LockoutPolicy`, gates on `email_verified` when
`Settings.auth_require_email_verification` is `True` (the default), and
emits `auth.*` audit events."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security.auth import AccountService, AuthService, EmailSender, build_get_current_principal
from app.core.security.auth.stores import (
    AuditAuthEventSink,
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserStore,
    build_account_service,
    build_lockout_policy,
    get_password_service,
    get_token_service,
    utc_now,
)
from app.core.security.auth.stores import get_email_sender as _resolve_email_sender


async def get_auth_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    """Per-request `AuthService`, bound to THIS request's `AsyncSession` —
    a fresh pair of store instances every call (they're thin wrappers
    holding only a session reference, so this is cheap), the process-wide
    `PasswordService` singleton (`get_password_service()` — see its own
    docstring on why that one IS cached), and a `TokenService` built fresh
    from `request.app.state.settings` (`get_token_service()` — raises
    `AuthNotConfiguredError`, fail-closed, if `jwt_signing_key` is unset;
    see that function's own docstring). `now=utc_now` is the SAME callable
    `get_token_service()` passes to the `TokenService` it builds — see
    that function's own module, `utc_now`'s docstring.

    Reads `request.app.state.settings` — the EXACT `Settings` instance
    `app/main.py`'s `create_app()` was actually constructed with (see that
    function's own comment on `app.state.settings`) — deliberately NOT
    `Depends(get_settings)`, the separate process-wide `lru_cache`d
    singleton every OTHER piece of this app's security composition
    (rate limiting, CORS, security headers) reads directly at
    APP-CONSTRUCTION time, not per-request. A route-level dependency has
    no other way to see a bespoke `Settings(...)` a caller passed to
    `create_app(settings=...)` instead of the cached singleton — see
    `tests/conftest.py`'s `make_client` fixture, which relies on exactly
    that seam to configure e.g. `jwt_signing_key` per test without
    mutating process env vars (which would leak across tests).

    Stage 5c (#45): additionally passes `lockout=build_lockout_policy(
    settings, db)` — the SAME `session` (`db`) `get_account_service` below
    builds its own `AccountService`'s `lockout=` from, when both are used
    within the same request/test — so a successful `AccountService.
    reset_password` can lift a lockout this `AuthService.login` recorded
    against the same account (see `build_lockout_policy`'s own docstring);
    `require_verification=settings.auth_require_email_verification`
    (secure default `True` — an unverified account cannot log in); and
    `events=AuditAuthEventSink()` so `login` emits its `auth.login`/
    `auth.lockout.triggered` audit events."""
    settings = request.app.state.settings
    return AuthService(
        users=SqlAlchemyUserStore(db),
        refresh_tokens=SqlAlchemyRefreshTokenStore(db),
        passwords=get_password_service(),
        tokens=get_token_service(settings),
        now=utc_now,
        lockout=build_lockout_policy(settings, db),
        require_verification=settings.auth_require_email_verification,
        events=AuditAuthEventSink(),
    )


def get_email_sender(request: Request) -> EmailSender:
    """FastAPI-dependency-shaped wrapper around `stores.get_email_sender(
    settings)` (imported here as `_resolve_email_sender` to avoid shadowing
    this function's own name) — a deliberately THIN seam whose only job is
    to be a distinct, overridable dependency callable: `get_account_service`
    below depends on THIS function via `Depends(get_email_sender)` rather
    than calling `stores.get_email_sender` directly, so a test can do
    `app.dependency_overrides[get_email_sender] = lambda: capturing_sender`
    and have `AccountService.request_email_verification`/
    `request_password_reset` hand their `EmailMessage` (raw verify/reset
    token included — see `_core.ConsoleEmailSender`'s own docstring on why
    that's the ONE place a raw token is deliberately surfaced) to that
    capturing sender instead of the real `ConsoleEmailSender`/
    `SmtpEmailSender` — a clean, deterministic way to read an issued token
    in a test without parsing a log string. Reads `request.app.state.
    settings`, matching `get_auth_service`/`get_account_service`'s own
    rationale for doing so rather than `Depends(get_settings)`."""
    settings = request.app.state.settings
    return _resolve_email_sender(settings)


async def get_account_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
) -> AccountService:
    """Per-request `AccountService` provider — the Stage 5c (#45) analogue
    of `get_auth_service` above, same session-per-request shape: delegates
    the rest of the composition to `stores.py:build_account_service(
    settings, db, email=email_sender)` (the SAME `db` session this request's
    `get_auth_service` — if also depended on within the same request —
    builds its own stores against, so a shared-session `LockoutPolicy` is
    possible; see that function's own docstring), but takes `email` as an
    explicit `Depends(get_email_sender)` argument rather than letting
    `build_account_service` re-resolve its own — see `get_email_sender`'s
    own docstring for why that's the seam a test overrides. Reads
    `request.app.state.settings`, matching `get_auth_service`'s own
    rationale for doing so rather than `Depends(get_settings)`."""
    settings = request.app.state.settings
    return build_account_service(settings, db, email=email_sender)


get_current_principal = build_get_current_principal(get_auth_service)
