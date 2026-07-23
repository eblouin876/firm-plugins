"""Package seam for the vendored auth component (`_core.py`, `_cookies.py`,
`django.py` — vendored from templates/components/security/auth/, see each
file's own header note). Same relative-import composition pattern as
rate_limiting/__init__.py — see that file's docstring.

Re-exports the names any in-app caller needs, so callers write
`from core.security.auth import AuthService` instead of reaching into the
individual vendored files. `core/security/auth/stores.py` (Stage 5b, #44;
NOT vendored — see that file's own module docstring) is this app's OWN
`UserStore`/`RefreshTokenStore` implementation plus
`get_password_service`/`get_token_service`/`build_auth_service` — it is
intentionally NOT re-exported here, the same "vendored vs. app code stay
in separate files, only the vendored half is re-exported by this package
seam" split `backend/fastapi`'s `app/core/security/auth/__init__.py`
documents for its own `stores.py` sibling; import it directly
(`from core.security.auth.stores import build_auth_service`).
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
from .django import (
    AUTH_ERROR_HTTP,
    InsufficientRole,
    clear_auth_cookies,
    enforce_csrf,
    read_refresh_cookie,
    require_roles,
    resolve_principal,
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
    "clear_auth_cookies",
    "enforce_csrf",
    "read_refresh_cookie",
    "require_roles",
    "resolve_principal",
    "set_auth_cookies",
]
