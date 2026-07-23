"""Stage 13d: the blog/CMS `Comment` model — a comment posted against one
`BlogPost`. THIS stage only needs the model plus the admin
list/hide/delete surface (`app/api/routers/blog.py`) — a public,
end-user-facing "create a comment" endpoint is explicitly OUT of scope
here (per the Stage 13 plan: "Comments are created by end-users in a
consuming app; THIS stage only needs the model + the ADMIN
moderation-ish endpoints"). Moderation proper (Flag/Report) is a LATER,
separate stage (13c) — not built here.

`body` is plain `Text`, never rendered as raw HTML anywhere in THIS
stage's own surface (the admin list/hide/delete endpoints only ever read
`body` back as an opaque string in `CommentOut`, never interpret it as
markup) — but ANY future write path that lets a caller set/replace
`Comment.body` (the eventual public create endpoint this stage
deliberately doesn't build) MUST go through the SAME
`app/services/sanitize.py:sanitize_blog_html()` this app's `BlogPost.
body_html` write-path already uses if that body is ever rendered as rich
text, or must be treated as plain text (escaped on render, never
interpreted as HTML) otherwise — never stored as raw, unsanitized,
attacker-controlled HTML. See that module's own docstring for the full
policy this warning points at.

`status` is a plain `String(16)`, NOT a DB-level enum — same `User.
status`/`BlogPost.status` precedent (see `app/models/blog_post.py`'s own
docstring), here over `{"visible", "hidden", "pending"}`
(`app/schemas/blog.py`'s `CommentStatus` `StrEnum`). Defaults `"visible"`
at both the Python/ORM and DB level.

`post_id` is a required, indexed FK to `BlogPost`; `author_id` is an
OPTIONAL FK to `User` (nullable — a comment's author may not correspond to
a registered `User` row in every consuming app's design, e.g. a
guest/anonymous commenter keyed some other way upstream; this stage
doesn't build that flow either, but the column is nullable so it doesn't
foreclose it). Both left at SQLAlchemy's/Postgres' default `ondelete`
(RESTRICT) — same "don't silently cascade away content" rationale
`BlogPost.author_id`'s own docstring documents, applied to both of this
model's own FKs."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Comment(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "blog_comments"

    post_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("blog_posts.id"),
        index=True,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=True,
        default=None,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain String(16), NOT a DB enum — see module docstring.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="visible", server_default="visible", index=True
    )
