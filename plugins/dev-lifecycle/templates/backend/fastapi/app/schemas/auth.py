"""Request/response schemas for the Stage 5 (#28) auth surface. Defined now
so the OpenAPI contract and the bearer security scheme are locked in Step 2
even though every route in app/api/routers/auth.py currently returns a
stub 501 — a real implementation slots in later without a schema/contract
change for a client already coded against these shapes.

STRICT (`extra="forbid"`) like every other wire schema in this catalog.
`TokenResponse`/`PrincipalOut`'s fields are a reasonable, conventional
guess at the eventual shape (access/refresh JWT pair; a minimal principal)
— Stage 5 is free to refine them, but a client generated against this
contract today is not left with nothing to bind to."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

# `email: str`, not `EmailStr` — EmailStr requires the `email-validator`
# extra (`pydantic[email]`), which is not in this block's pinned dependency
# set (see pyproject.toml). Stage 5 (#28), which actually implements this
# surface, can add that extra then if real email validation is wanted.


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class PrincipalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str
