"""Auth STUBS — gate-1 "define+stub": request/response schemas and the
bearer security scheme are real and locked into the OpenAPI contract now,
but every handler body returns HTTP 501 without touching a database or
issuing a real token. Full implementation (password/credential
verification, JWT issuance, refresh rotation, principal resolution) lands
in Stage 5 (#28) — this router exists so Stage 5 has a stable route/schema
surface to fill in, not a blank page.

JUDGMENT CALL: these 501s are raised as a plain `HTTPException`
(`{"detail": "..."}`), deliberately bypassing the `ErrorEnvelope` a real
error response uses elsewhere in this app. `ErrorCode` (app/core/errors.py)
is a LOCKED, versioned enum with no `not_implemented` member — adding one
for a temporary stub is exactly the kind of contract change that module's
own docstring says needs the same coordination as any other wire-shape
edit (bump the generated API client, keep Stage 4's Django/DRF code set
aligned). A plain, undocumented-in-the-envelope 501 is the documented
"stub" response instead; Stage 5 replaces both the body and, if it turns
out a `not_implemented`-shaped envelope is ever needed elsewhere, that's a
real contract proposal at that point, not something Step 2 should decide
unilaterally for a route with no implementation behind it yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from starlette import status

from app.api.deps import get_current_principal
from app.schemas.auth import LoginRequest, PrincipalOut, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_STUB_DETAIL = "Not implemented — lands in Stage 5 (#28)."


@router.post("/login", response_model=TokenResponse, summary="Login (stub)")
async def login(payload: LoginRequest) -> TokenResponse:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_STUB_DETAIL)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh token (stub)")
async def refresh(payload: RefreshRequest) -> TokenResponse:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_STUB_DETAIL)


@router.get("/me", response_model=PrincipalOut, summary="Current principal (stub)")
async def me(_principal: None = Depends(get_current_principal)) -> PrincipalOut:
    # get_current_principal() already raises 501 unconditionally (see
    # app/api/deps.py) — this line never runs, but response_model/the
    # bearer-scheme Depends() above are what lock the OpenAPI contract in.
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_STUB_DETAIL)
