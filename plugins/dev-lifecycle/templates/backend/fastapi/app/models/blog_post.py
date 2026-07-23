"""Stage 13d: the blog/CMS `BlogPost` model — built on the same vendored
`app/core/db/mixins.py` composition every other model in this catalog
uses (`UUIDPrimaryKey` + `TimestampMixin` + `SoftDeleteMixin`, the `User`/
`Item` precedent), plus one owning FK to `User`. Not a vendored file
itself, same posture as `app/models/user.py`.

`body_json` (the raw ProseMirror document the — later, Stage 13d UI —
TipTap editor produces) is stored OPAQUE, a plain JSON column with no
schema of its own at this layer: it's the source of truth for RE-EDITING
a post (reloaded into the editor in the authenticated admin context only),
never rendered anywhere public. `body_html` is the SANITIZED render
source of truth — `app/services/sanitize.py`'s `sanitize_blog_html()` is
called on it by the write-path (`app/api/routers/blog.py`'s create/update
handlers) BEFORE this column is ever written; nothing outside that one
seam is trusted to have already sanitized it. See that module's own
docstring for the full render rule this model's two body columns embody:
"only `body_html` is ever rendered; `body_json` is only reloaded into the
editor."

`status` is a plain `String(16)`, NOT a DB-level enum — the SAME `User.
status` precedent (`app/models/user.py`'s own docstring: "a DB enum type
is a schema-migration event of its own to add/remove a member, and this
app's hermetic sqlite test suite needs a column type sqlite actually
has"), applied here to `{"draft", "published"}` (`app/schemas/blog.py`'s
`BlogPostStatus` `StrEnum` is the app-level closed set). Defaults `"draft"`
at both the Python/ORM level and the DB level (`server_default="draft"`),
same two-layer shape `User.status` documents.

`author_id` is a required FK to `User`, left at SQLAlchemy's/Postgres'
default `ondelete` (RESTRICT/no explicit `ondelete=` — the SAME choice
`app/models/refresh_token.py`'s `RefreshToken.user_id` documents: deleting
a `User` row while it still owns `BlogPost` rows is refused by the
database rather than silently cascading away authored content or orphaning
it to a NULL author). Neither this app nor `backend/django` ever
hard-deletes a `User` row today (both use `SoftDeleteMixin`/`User.
mark_deleted` instead), so this constraint isn't exercised in practice —
it's still the correct default for a security/content-integrity-relevant
child table, matching that same migration's own rationale."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class BlogPost(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "blog_posts"

    # UNIQUE — the human-readable, URL-safe identifier
    # (`app/schemas/blog.py`'s `^[a-z0-9-]+$` pattern validates the SHAPE
    # at the request boundary; this index is the DB-level enforcement of
    # last resort against a concurrent duplicate-slug write, the same
    # "friendly-error-path plus DB-enforced backstop" split
    # `alembic/versions/0002_create_auth_tables.py`'s own docstring
    # documents for `users.email`). 220 chars — comfortably above
    # `title`'s own 200-char cap plus room for a numeric
    # collision-disambiguation suffix (`app/api/routers/blog.py`'s
    # `_unique_slug`).
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Opaque ProseMirror doc — see module docstring.
    body_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # SANITIZED render source of truth — see module docstring. `Text`, not
    # `String(n)`: sanitized rich-text HTML has no fixed reasonable cap the
    # way a title/slug does.
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain String(16), NOT a DB enum — see module docstring.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft", index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    author_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
