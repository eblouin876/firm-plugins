"""Request/response schemas for the moderation admin surface
(`app/api/routers/moderation.py`, Stage 13c) — mirrors `app/schemas/
admin.py`/`app/schemas/blog.py`'s plain-`BaseModel` + `ConfigDict(extra=
"forbid")` posture (this family of schemas lives under the same `/admin/*`
surface as `AdminUserOut`/`BlogPostOut`, so it follows that precedent
rather than `app/schemas/item.py`'s `StrictModel`).

`FlagTargetType`/`FlagStatus`/`ResolveAction` are the app-level, CLOSED
sets `app/models/flag.py`'s `target_type`/`status` columns actually store
(plus the resolve action verb, which isn't a column at all — it's the
request body's own dispatch key). `StrEnum`, matching `app/schemas/
admin.py`'s `UserStatus`/`app/schemas/blog.py`'s `BlogPostStatus`
precedent, so an unrecognized `?status=`/`?target_type=` query value or an
unrecognized `action` in a resolve request body 422s automatically."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class FlagTargetType(StrEnum):
    BLOG_POST = "blog_post"
    COMMENT = "comment"
    USER = "user"


class FlagStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ResolveAction(StrEnum):
    """The four verbs `POST /admin/flags/{flag_id}/resolve` dispatches on
    — see `app/api/routers/moderation.py`'s `resolve_admin_flag` for the
    full per-action behavior each one triggers against the flag's
    `target_type`."""

    NONE = "none"
    HIDE_CONTENT = "hide_content"
    DELETE_CONTENT = "delete_content"
    BAN_AUTHOR = "ban_author"


class FlagOut(BaseModel):
    """The read shape every moderation admin endpoint returns.
    `from_attributes=True` lets `FlagOut.model_validate(flag)` read
    straight off the ORM instance, the same convention `app/schemas/
    admin.py`'s `AdminUserOut`/`app/schemas/blog.py`'s `BlogPostSummaryOut`
    document."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    target_type: FlagTargetType
    target_id: uuid.UUID
    reporter_id: uuid.UUID | None
    reason: str
    status: FlagStatus
    resolved_by_id: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime


class FlagResolveIn(BaseModel):
    """`POST /admin/flags/{flag_id}/resolve`'s request body — `action`
    picks which content/author-side effect (if any) the resolve also
    performs (see `ResolveAction`'s own docstring); `note` is an optional
    free-text resolution note, persisted verbatim to `Flag.
    resolution_note` (never rendered as markup anywhere in this app — same
    "opaque, never sanitized" posture `app/models/comment.py`'s own
    docstring documents for a plain-text column with no render path)."""

    model_config = ConfigDict(extra="forbid")

    action: ResolveAction
    note: str | None = None


class FlagDismissIn(BaseModel):
    """`POST /admin/flags/{flag_id}/dismiss`'s request body — no content
    action, ever; `note` is the same optional free-text resolution note
    `FlagResolveIn.note` documents."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = None
