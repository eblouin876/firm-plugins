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
future protected route)."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security.auth import AuthService, build_get_current_principal
from app.core.security.auth.stores import (
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserStore,
    get_password_service,
    get_token_service,
    utc_now,
)


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
    mutating process env vars (which would leak across tests)."""
    settings = request.app.state.settings
    return AuthService(
        users=SqlAlchemyUserStore(db),
        refresh_tokens=SqlAlchemyRefreshTokenStore(db),
        passwords=get_password_service(),
        tokens=get_token_service(settings),
        now=utc_now,
    )


get_current_principal = build_get_current_principal(get_auth_service)
