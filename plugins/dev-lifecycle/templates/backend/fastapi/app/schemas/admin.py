"""Request/response schemas for the admin user-management surface
(`app/api/routers/admin.py`, Stage 13b) — mirrors `app/schemas/auth.py`'s
plain-`BaseModel` + `ConfigDict(extra="forbid")` posture (not
`app/schemas/item.py`'s `StrictModel`, which this family of schemas has no
documented need for either) rather than inventing a third schema-authoring
convention for one new router.

`UserStatus` is the app-level, CLOSED set of values `app/models/user.py`'s
`User.status` column actually stores — `"active"`/`"suspended"`/`"banned"`,
a plain `String(16)`, never a DB-level enum (see that column's own
docstring). A `StrEnum` here (matching `app/core/errors.py`'s own
`ErrorCode` precedent) is what turns an unrecognized `?status=` query value
into FastAPI's native 422 automatically, and what documents a proper OpenAPI
enum on `AdminUserOut.status` for the generated client to switch on."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"


class AdminUserOut(BaseModel):
    """The read shape every admin user-management endpoint returns.
    Deliberately NO `password_hash`, NO token fields — this is the ONE
    place `app/models/user.py`'s `User` ORM instance is ever serialized for
    an admin caller, and leaking either would be a straightforward secret
    leak into an HTTP response (and, via `app/api/routers/admin.py`'s own
    `audit_event(...)` calls, never into an audit log either — see that
    router's module docstring). `from_attributes=True` lets
    `AdminUserOut.model_validate(user)` read straight off the ORM
    instance's attributes, the same convention `app/schemas/item.py`'s
    `ItemOut` documents."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    email: str
    roles: list[str]
    status: UserStatus
    email_verified: bool
    created_at: datetime


class AdminRolesIn(BaseModel):
    """`PUT /admin/users/{user_id}/roles`'s request body — a full-replace
    role list (not a delta/patch), validated at the ROUTE layer
    (`app/api/routers/admin.py`'s `set_admin_user_roles`) against the
    app's own closed allowed-role set — this schema only enforces "a list
    of strings", never which strings, since the allowed set is a small,
    app-level policy decision, not a wire-shape constraint `extra="forbid"`
    can express."""

    model_config = ConfigDict(extra="forbid")

    roles: list[str] = Field(default_factory=list)
