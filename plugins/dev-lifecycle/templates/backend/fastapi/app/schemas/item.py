"""Request/response schemas for `Item` — strict Pydantic v2 (`extra="forbid"`
throughout, matching this catalog's reject-don't-drop posture in
error-envelope/ and pagination/schema.py), kept separate from
app/models/item.py's SQLAlchemy model per references/backend/pydantic.md's
"Schema design" (never reuse an ORM model as a request/response body)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ItemCreate(ItemBase):
    """The create-body schema — everything `ItemBase` declares, required as
    specified there (`name` required, `description` optional)."""


class ItemUpdate(BaseModel):
    """The update-body schema — every field optional, so a client can PATCH
    a subset. The route maps only explicitly-set fields
    (`model_dump(exclude_unset=True)`) onto the existing row."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ItemOut(ItemBase):
    """The read schema — adds the DB-generated fields (`id`, timestamps).
    `from_attributes=True` is what lets `ItemOut.model_validate(orm_obj)`
    read straight off the SQLAlchemy instance's attributes (see
    references/backend/pydantic.md's v2 config note)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
