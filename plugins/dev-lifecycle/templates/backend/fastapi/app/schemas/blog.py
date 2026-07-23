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

import json
import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The same shape validated at the request boundary (Field(pattern=...)
# below) AND used by app/api/routers/blog.py to slugify a title when no
# slug is supplied — kept here, not duplicated in the router, so the
# ONE regex both call sites rely on can't drift.
SLUG_PATTERN = r"^[a-z0-9-]+$"

# Defense-in-depth size caps on the two body columns (`app/models/
# blog_post.py`'s `body_html`/`body_json`) — this write-path is already
# admin-gated (`require_admin`) and rate-limited (`require_admin_rate_
# limit`, `app/api/routers/blog.py`), so an unbounded body isn't an
# open/anonymous attack surface; these caps are a generous, documented
# backstop against a compromised/careless admin session (or a buggy
# editor client) persisting an unbounded payload, not a tight editorial
# limit. `body_html` (sanitized rich-text render source): 1,000,000 chars
# (~1 MB) — comfortably above any real blog post's rendered HTML while
# still bounding storage/response-payload size. `body_json` (the raw
# ProseMirror doc): same ~1 MB ceiling on its SERIALIZED (`json.dumps`)
# size, checked in `BlogPostCreate`/`BlogPostUpdate`'s `_check_body_json_size`
# validator below — a `dict` has no `max_length` of its own the way a
# `str` does, so the cap is enforced on the JSON-encoded byte count
# instead, the same quantity `body_html`'s cap bounds.
_BODY_HTML_MAX_CHARS = 1_000_000
_BODY_JSON_MAX_SERIALIZED_CHARS = 1_000_000


def _check_body_json_size(value: dict[str, Any]) -> dict[str, Any]:
    serialized_len = len(json.dumps(value))
    if serialized_len > _BODY_JSON_MAX_SERIALIZED_CHARS:
        raise ValueError(
            f"body_json is too large: serialized size {serialized_len} exceeds the "
            f"{_BODY_JSON_MAX_SERIALIZED_CHARS}-character cap."
        )
    return value


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
    body_html: str = Field(max_length=_BODY_HTML_MAX_CHARS)

    _check_body_json_size = field_validator("body_json")(_check_body_json_size)


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
    body_html: str | None = Field(default=None, max_length=_BODY_HTML_MAX_CHARS)

    @field_validator("body_json")
    @classmethod
    def _check_body_json_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        # `None` here means "explicitly nulled" (an omitted field never
        # reaches a validator at all, matching `BlogPostCreate`'s own
        # `_check_body_json_size`'s docstring elsewhere in this module) —
        # `_reject_explicit_null` below is what turns that into a 422, so
        # this validator has nothing to size-check for a `None` value and
        # just passes it through unchanged.
        if value is None:
            return value
        return _check_body_json_size(value)

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> BlogPostUpdate:
        offending = sorted(
            field
            for field in ("title", "slug", "body_json", "body_html")
            if field in self.model_fields_set and getattr(self, field) is None
        )
        if offending:
            raise ValueError(f"Field(s) cannot be explicitly null: {', '.join(offending)}")
        return self


class PublicBlogPostSummaryOut(BaseModel):
    """The PUBLIC list shape (`GET /blog/posts`, `app/api/routers/
    blog_public.py`) — deliberately NOT `BlogPostSummaryOut` (the admin
    list shape) reused/subclassed: this schema omits `status` entirely (a
    public reader only ever sees published posts, so the field would be a
    constant, content-free `"published"` on every row — and, more to the
    point, echoing status back at all invites a future caller to build UI
    branching on a value this surface has no business exposing, see this
    stage's own security posture: "no internal status transitions") and
    ADDS `excerpt` (below), which the admin shape has no need for. NO
    `body_json`, NO `body_html` — matching the plan's own contract table
    ("Summary = id, title, slug, excerpt-or-nothing, published_at,
    author_id, created_at — NO body"). `author_id` only (never an email or
    any other PII) — same posture `BlogPostSummaryOut` already documents,
    just restated here since this schema doesn't inherit its docstring."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    published_at: datetime
    author_id: uuid.UUID
    created_at: datetime


class PublicBlogPostOut(PublicBlogPostSummaryOut):
    """The PUBLIC single-post shape (`GET /blog/posts/{slug}`) —
    `PublicBlogPostSummaryOut` plus the ONE body field a public reader may
    ever see: `body_html`, always the value `app/services/sanitize.py:
    sanitize_blog_html()` already cleaned at write time (this schema
    re-sanitizes nothing — see that module's own "only body_html is ever
    rendered" render rule). **`body_json` is NEVER a field on this schema,
    full stop** — it is the opaque ProseMirror editor source `BlogPostOut`
    (the ADMIN single-post shape) carries for the authenticated editor to
    reload, and rendering it publicly (e.g. via some future ProseMirror-
    to-HTML path that bypasses the sanitizer) would reopen the exact
    stored-XSS hole `sanitize_blog_html()` exists to close — see that
    module's own docstring, "Any future public-facing blog render endpoint
    MUST render `body_html` and MUST NOT render `body_json`.\""""

    body_html: str


_EXCERPT_MAX_CHARS = 200
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")


def derive_excerpt(body_html: str) -> str | None:
    """Plain-text excerpt for `PublicBlogPostSummaryOut.excerpt` — derived
    at READ time from the already-sanitized `body_html`, never stored as
    its own column (this stage's contract table calls it "excerpt-or-
    nothing", not a new writable field the admin surface has to grow a
    concept of). Strips every HTML tag (a bare regex, not `nh3` — safe
    here specifically because `body_html` is ALREADY `sanitize_blog_html()`
    -cleaned by the time this runs, so there is no attacker-controlled
    markup left to mis-parse; this function only ever produces plain JSON
    string content, never re-embeds anything as HTML), collapses
    whitespace, tidies the stray space a tag-boundary substitution can
    leave before punctuation (`"world , "` -> `"world, "` — a tag removed
    right before a comma/period/etc. that immediately followed inline
    markup, e.g. `<strong>world</strong>,`), and truncates to
    `_EXCERPT_MAX_CHARS` at the last whole word boundary (falling back to
    a hard character cut only if the first `_EXCERPT_MAX_CHARS` characters
    contain no space at all), appending a single `"…"` when truncated.
    Returns `None` — never `""` — for a post whose body strips down to
    nothing (an all-markup, no-text body): the "-or-nothing" half of
    "excerpt-or-nothing".

    Mirrored BYTE-IDENTICALLY in `core/serializers.py`'s `derive_excerpt`
    on the Django track — a divergence between the two is a parity bug,
    the same posture `slugify` (above) already documents for itself."""
    text = _WHITESPACE_RE.sub(" ", _HTML_TAG_RE.sub(" ", body_html)).strip()
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", text)
    if not text:
        return None
    if len(text) <= _EXCERPT_MAX_CHARS:
        return text
    truncated = text[:_EXCERPT_MAX_CHARS].rsplit(" ", 1)[0].rstrip()
    if not truncated:
        truncated = text[:_EXCERPT_MAX_CHARS].rstrip()
    return truncated + "…"


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
