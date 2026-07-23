"""Request/response schemas for the blog/CMS admin surface
(`app/api/routers/blog.py`, Stage 13d) — mirrors `app/schemas/admin.py`'s
plain-`BaseModel` + `ConfigDict(extra="forbid")` posture (this family of
schemas lives under the same `/admin/*` surface as `AdminUserOut`/
`AdminRolesIn`, so it follows that precedent rather than `app/schemas/
item.py`'s `StrictModel`).

`BlogPostStatus`/`CommentStatus` are the app-level, CLOSED sets
`app/models/blog_post.py`'s `BlogPost.status` / `app/models/comment.py`'s
`Comment.status` actually store — plain `String(16)` columns, never DB
enums (see each model's own docstring). `StrEnum`, matching `app/schemas/
admin.py`'s `UserStatus` precedent, so an unrecognized `?status=` query
value 422s automatically and the generated client gets a proper enum to
switch on.

**Never renders `body_json` publicly.** `BlogPostOut` DOES include
`body_json` — but only on the single-post GET/create/update responses,
which are ALL admin-gated (`require_admin`, `app/api/routers/blog.py`).
`BlogPostSummaryOut` (the LIST shape) omits both body fields entirely.
There is no public, unauthenticated render endpoint in this stage — see
`app/services/sanitize.py`'s own docstring for the render rule this
split enforces ("only `body_html` is ever rendered; `body_json` is only
reloaded into the editor")."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The same shape validated at the request boundary (Field(pattern=...)
# below) AND used by app/api/routers/blog.py to slugify a title when no
# slug is supplied — kept here, not duplicated in the router, so the
# ONE regex both call sites rely on can't drift.
SLUG_PATTERN = r"^[a-z0-9-]+$"


class BlogPostStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class CommentStatus(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    PENDING = "pending"


class BlogPostSummaryOut(BaseModel):
    """The LIST shape (`GET /admin/blog/posts`) — deliberately NO body
    fields (`body_json`/`body_html`) at all, matching the plan's own
    endpoint contract table. `from_attributes=True` lets `BlogPostSummaryOut.
    model_validate(post)` read straight off the ORM instance, same
    convention `app/schemas/admin.py`'s `AdminUserOut` documents."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    status: BlogPostStatus
    published_at: datetime | None
    author_id: uuid.UUID
    created_at: datetime


class BlogPostOut(BlogPostSummaryOut):
    """The single-post shape (`GET`/`POST`/`PATCH .../posts/{post_id}`,
    `.../publish`, `.../unpublish`) — `BlogPostSummaryOut` plus both body
    columns. `body_html` here is ALWAYS the sanitized value already
    persisted (`app/services/sanitize.py`) — this schema never re-runs or
    bypasses sanitization; it only reads back what the write-path already
    cleaned."""

    body_json: dict[str, Any]
    body_html: str


class BlogPostCreate(BaseModel):
    """`POST /admin/blog/posts`'s request body. `slug` is OPTIONAL — when
    omitted, `app/api/routers/blog.py`'s `create_admin_blog_post` derives
    one from `title` (slugify + auto-disambiguate on collision, NEVER a
    409 for the derived case — the caller didn't choose it). An
    EXPLICITLY supplied `slug` that collides with an existing post's slug
    is a 409 `conflict` instead (see that handler's own docstring) — this
    schema only enforces the wire SHAPE (`^[a-z0-9-]+$`, `Field(pattern=
    ...)` below — an invalid shape is a 422, at the request boundary,
    before the handler's uniqueness check ever runs).

    `body_json`/`body_html` are both REQUIRED — a post is created with its
    initial ProseMirror doc and HTML render already in hand (this stage
    builds no separate "create an empty draft" flow). `body_html` is
    RAW/UNTRUSTED input at this layer — `create_admin_blog_post` is what
    sanitizes it before persisting; this schema does not, and must not,
    pre-sanitize (that would hide what the write-path itself is
    responsible for, and this schema has no way to prove IT ran instead
    of some other, unaudited call site)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=220, pattern=SLUG_PATTERN)
    body_json: dict[str, Any]
    body_html: str


class BlogPostUpdate(BaseModel):
    """`PATCH /admin/blog/posts/{post_id}`'s request body — every field
    optional, so a client can PATCH a subset; the route maps only
    explicitly-set fields (`model_dump(exclude_unset=True)`) onto the
    existing row, the same `ItemUpdate` convention (`app/schemas/item.py`).

    Every one of these four columns is NOT NULL at the DB level (`app/
    models/blog_post.py`) — unlike `app/schemas/item.py`'s `ItemUpdate.
    name` (a documented, NOT mirrored, divergence — see `tests/
    test_schema_conformance.py`'s `_KNOWN_DIVERGENCES` on the Django
    track), this schema does NOT leave an explicit `{"title": null}`
    accepted-then-crashing: `_reject_explicit_null` below rejects it as a
    422 at the schema layer itself, so `app/api/routers/blog.py`'s
    `update_admin_blog_post` never has to guess whether a `None` in
    `model_dump(exclude_unset=True)` means "field omitted" (impossible,
    `exclude_unset` already filters those out) or "field explicitly
    nulled" (now impossible too, rejected here)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=220, pattern=SLUG_PATTERN)
    body_json: dict[str, Any] | None = None
    body_html: str | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "BlogPostUpdate":
        offending = sorted(
            field
            for field in ("title", "slug", "body_json", "body_html")
            if field in self.model_fields_set and getattr(self, field) is None
        )
        if offending:
            raise ValueError(f"Field(s) cannot be explicitly null: {', '.join(offending)}")
        return self


class CommentOut(BaseModel):
    """The shape every blog-comment admin endpoint returns
    (`GET /admin/blog/comments`, `POST .../hide`) — matches the plan's
    table exactly: `id`, `post_id`, `author_id`, `body`, `status`,
    `created_at`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    status: CommentStatus
    created_at: datetime


def slugify(title: str) -> str:
    """Derives a `SLUG_PATTERN`-conformant slug from `title` — lowercase,
    non-`[a-z0-9]` runs collapsed to a single `-`, leading/trailing `-`
    stripped. Falls back to a fixed, still-pattern-conformant literal
    (`"post"`) for a title that slugifies to nothing at all (e.g. a title
    that's pure punctuation/whitespace/non-ASCII with no `[a-z0-9]`
    characters) — `app/api/routers/blog.py`'s `_unique_slug` still runs
    its own collision-disambiguation loop on top of whatever this
    returns, so multiple such titles don't collide with each other
    either."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "post"
