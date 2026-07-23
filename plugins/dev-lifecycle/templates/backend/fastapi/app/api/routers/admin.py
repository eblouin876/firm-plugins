"""RBAC admin example (Stage 5d, #46) -- `GET /admin/ping`, gated by
`require_admin` (`app/api/deps.py`: `require_roles(get_current_principal,
"admin")`, from the vendored auth component's `fastapi.py`). Demonstrates
the role-gating machinery end to end, with no new auth logic of its own:

- **200** for an authenticated principal whose `AccessClaims.roles`
  includes `"admin"`.
- **403** `permission_denied` for an authenticated principal WITHOUT the
  `"admin"` role -- `require_roles`'s dependency raises `InsufficientRole`
  (`app/core/security/auth/fastapi.py`), mapped by `app/main.py`'s
  `_auth_error_handler` via the vendored component's `AUTH_ERROR_HTTP`
  table.
- **401** `unauthenticated` for a missing/malformed/expired bearer token --
  `get_current_principal` (which `require_admin` itself depends on) raises
  `InvalidToken` before this handler's body, or even `require_admin`'s own
  role check, ever runs.

Every one of those three outcomes is entirely the existing `get_current_
principal`/`require_roles`/`AuthError`-handler machinery already proven by
`GET /auth/me` and `tests/test_auth.py` -- this router adds no new
authentication or authorization code, only a route to exercise it as an
admin-only example.

Reuses `HealthStatus` (`app/schemas/health.py`, `{"status": str}`) as the
response shape rather than inventing a near-identical model -- this
endpoint's own success body is exactly `{"status": "ok"}`, the shape
`HealthStatus` already is (see that schema's own docstring)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.errors import ErrorEnvelope
from app.schemas.health import HealthStatus

router = APIRouter(prefix="/admin", tags=["admin"])

# Mirrors app/api/routers/auth.py's own `_UNAUTHENTICATED_RESPONSE`/
# `_CONFLICT_RESPONSE` pattern (documenting the ErrorEnvelope-shaped error
# responses this route actually sends at runtime, via app/main.py's
# `_auth_error_handler`) -- both entries this route can actually produce,
# gathered in one place rather than inlined in the decorator below.
_AUTH_RESPONSES = {
    401: {"model": ErrorEnvelope, "description": "Missing or invalid bearer token."},
    403: {"model": ErrorEnvelope, "description": "Authenticated, but the caller lacks the 'admin' role."},
}


@router.get(
    "/ping",
    response_model=HealthStatus,
    summary="Admin ping",
    # Explicit, stable operationId (Stage 5d task contract) rather than
    # FastAPI's own auto-derived one -- pinning it here means a later
    # rename of this function/module never silently renames the generated
    # client's method for it.
    operation_id="admin_ping_admin_ping_get",
    dependencies=[Depends(require_admin)],
    responses=_AUTH_RESPONSES,
)
async def admin_ping() -> HealthStatus:
    """`require_admin` (declared in `dependencies=` above, not as a bound
    parameter -- this handler needs nothing from the resolved principal,
    only the gate itself) already verified the bearer token AND the
    `"admin"` role before this body ever runs. `HTTPBearer` (via
    `require_admin` -> `get_current_principal` -> the vendored component's
    `bearer_scheme`) is picked up in this operation's OpenAPI `security`
    the same way it already is for `GET /auth/me` -- FastAPI resolves
    security schemes from the full dependency tree, not just parameters
    bound directly on the route function, so declaring the gate via
    `dependencies=[Depends(require_admin)]` documents it in the schema
    exactly as if it were a direct parameter."""
    return HealthStatus(status="ok")
