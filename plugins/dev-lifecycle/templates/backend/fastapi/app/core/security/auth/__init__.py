"""Package seam for the vendored auth component (`_core.py`, `_cookies.py`,
`fastapi.py` — vendored from templates/components/security/auth/, see each
file's own header note). Same relative-import composition pattern as
security_headers/__init__.py and rate_limiting/__init__.py — see either
file's docstring.

Re-exports the names the rest of this app needs so callers write
`from app.core.security.auth import AuthService, AccessClaims,
build_get_current_principal` instead of reaching into the individual
vendored files. The SQLAlchemy-backed `UserStore`/`RefreshTokenStore`
implementations and the per-request `AuthService` provider are NOT part of
this package — those import `app.models` (a DB-layer, app-specific
concern), so they live in `app/core/security/auth/stores.py`, which is
this app's own code, not a vendored file (see that module's own docstring
and this component's README's "app wiring" note).
"""

from __future__ import annotations

from ._core import (
    AccessClaims,
    AccountService,
    AttemptRecord,
    AuthError,
    AuthEventSink,
    AuthService,
    ConsoleEmailSender,
    EmailAlreadyExists,
    EmailMessage,
    EmailSender,
    InvalidCredentials,
    InvalidSingleUseToken,
    InvalidToken,
    LockoutPolicy,
    LockoutStore,
    PasswordService,
    RefreshClaims,
    RefreshRecord,
    RefreshTokenStore,
    SingleUseTokenRecord,
    SingleUseTokenService,
    SingleUseTokenStore,
    TokenPair,
    TokenReused,
    TokenService,
    UserRecord,
    UserStore,
    hash_token,
)
from ._cookies import (
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    CsrfValidationError,
    build_csrf_cookie_kwargs,
    build_refresh_cookie_kwargs,
    clear_csrf_cookie_kwargs,
    clear_refresh_cookie_kwargs,
    generate_csrf_token,
    verify_double_submit,
)
from .fastapi import (
    AUTH_ERROR_HTTP,
    InsufficientRole,
    bearer_scheme,
    build_get_current_principal,
    clear_auth_cookies,
    enforce_csrf,
    read_refresh_cookie,
    require_roles,
    set_auth_cookies,
)

__all__ = [
    "AccessClaims",
    "AccountService",
    "AttemptRecord",
    "AuthError",
    "AuthEventSink",
    "AuthService",
    "ConsoleEmailSender",
    "EmailAlreadyExists",
    "EmailMessage",
    "EmailSender",
    "InvalidCredentials",
    "InvalidSingleUseToken",
    "InvalidToken",
    "LockoutPolicy",
    "LockoutStore",
    "PasswordService",
    "RefreshClaims",
    "RefreshRecord",
    "RefreshTokenStore",
    "SingleUseTokenRecord",
    "SingleUseTokenService",
    "SingleUseTokenStore",
    "TokenPair",
    "TokenReused",
    "TokenService",
    "UserRecord",
    "UserStore",
    "hash_token",
    "CSRF_COOKIE_NAME",
    "REFRESH_COOKIE_NAME",
    "CsrfValidationError",
    "build_csrf_cookie_kwargs",
    "build_refresh_cookie_kwargs",
    "clear_csrf_cookie_kwargs",
    "clear_refresh_cookie_kwargs",
    "generate_csrf_token",
    "verify_double_submit",
    "AUTH_ERROR_HTTP",
    "InsufficientRole",
    "bearer_scheme",
    "build_get_current_principal",
    "clear_auth_cookies",
    "enforce_csrf",
    "read_refresh_cookie",
    "require_roles",
    "set_auth_cookies",
]
