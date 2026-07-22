"""Shared FastAPI dependencies. `get_current_principal` is the Step 3 /
Stage 5 (#28) seam: it declares the bearer security scheme in OpenAPI (via
`fastapi.security.HTTPBearer` used as a dependency) and gives every future
protected route one name to depend on, but does not implement any real
token verification yet — see its own docstring for exactly what it does
today and why.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.exceptions import HTTPException
from starlette import status

# `auto_error=False`: a missing Authorization header should reach this
# dependency's own body (which raises the documented stub response) rather
# than HTTPBearer's own default 403 — keeping ONE documented failure mode
# for "auth isn't implemented yet" instead of two different shapes
# depending on whether a header was even sent.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """STUB dependency — real principal resolution (JWT verification,
    session/user lookup) is implemented in Stage 5 (#28). Using
    `HTTPBearer()` as a dependency is what registers the `HTTPBearer`
    security scheme in the app's generated OpenAPI (`components.
    securitySchemes`) the first time any route depends on this — no manual
    OpenAPI patching needed in app/main.py.

    Unconditionally raises a plain `HTTPException(501)` (bypassing the
    `ErrorEnvelope`/`AppError` hierarchy in app/core/errors.py — see
    app/api/routers/auth.py's module docstring for why: `not_implemented`
    is not a member of the LOCKED `ErrorCode` set, and adding one is a
    contract change out of scope for Step 2). Any real protected route
    wired to this dependency in the meantime fails closed (denies) rather
    than silently allowing access, matching
    references/security/secure-baseline.md's "Audit logging" fail-closed
    posture — it just fails closed with a 501, not yet a 401/403, because
    the check itself doesn't exist yet."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authentication is not yet implemented (Stage 5, #28).",
    )
