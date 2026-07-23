"""Request/response schemas for the auth surface (`app/api/routers/auth.py`).
Stage 3 Step 2 locked the OpenAPI contract and bearer security scheme in
before any handler had a real body; Stage 5a (#41) is the implementation
that actually reads/writes these shapes end to end (register/login/refresh/
logout/me), against the vendored auth component's `AuthService`.

STRICT (`extra="forbid"`) like every other wire schema in this catalog.
`RegisterRequest` is new in Stage 5a — `POST /auth/register` didn't exist
before. `PrincipalOut` stays `{id, email}` only — no `roles` on the wire in
this stage; RBAC's wire surface is Stage 5d, deliberately out of scope
here even though `_core.AccessClaims`/`UserRecord` already carry roles
internally."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

# `email: str`, not `EmailStr` — EmailStr requires the `email-validator`
# extra (`pydantic[email]`), which is not in this block's pinned dependency
# set (see pyproject.toml). Real email FORMAT validation isn't added in
# Stage 5a either — `_core.AuthService`'s own normalization (lowercase +
# strip, see its `_normalize_email`) is the only shaping applied; a
# malformed-but-non-empty string is accepted as an email today. A future
# stage can add the `pydantic[email]` extra + switch to `EmailStr` if real
# format validation is wanted.


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


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
