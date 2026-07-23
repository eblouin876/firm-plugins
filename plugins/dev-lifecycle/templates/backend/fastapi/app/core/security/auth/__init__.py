"""Package seam for the vendored auth component (`_core.py`, `fastapi.py` —
vendored from templates/components/security/auth/, see each file's own
header note). Same relative-import composition pattern as
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
    AuthError,
    AuthService,
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    PasswordService,
    RefreshClaims,
    RefreshRecord,
    RefreshTokenStore,
    TokenPair,
    TokenReused,
    TokenService,
    UserRecord,
    UserStore,
    hash_token,
)
from .fastapi import (
    AUTH_ERROR_HTTP,
    InsufficientRole,
    bearer_scheme,
    build_get_current_principal,
    require_roles,
)

__all__ = [
    "AccessClaims",
    "AuthError",
    "AuthService",
    "EmailAlreadyExists",
    "InvalidCredentials",
    "InvalidToken",
    "PasswordService",
    "RefreshClaims",
    "RefreshRecord",
    "RefreshTokenStore",
    "TokenPair",
    "TokenReused",
    "TokenService",
    "UserRecord",
    "UserStore",
    "hash_token",
    "AUTH_ERROR_HTTP",
    "InsufficientRole",
    "bearer_scheme",
    "build_get_current_principal",
    "require_roles",
]
