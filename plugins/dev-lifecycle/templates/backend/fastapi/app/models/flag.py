"""Stage 13c: the moderation `Flag` model — an admin-only moderation queue.
Built on the SAME vendored `app/core/db/mixins.py` composition every other
model in this catalog uses (`UUIDPrimaryKey` + `TimestampMixin` +
`SoftDeleteMixin`, the `User`/`BlogPost`/`Comment` precedent). Not a
vendored file itself, same posture as `app/models/blog_post.py`.

**Admin-only queue, no end-user write path.** This stage ships the model
plus the admin moderation queue + resolve/dismiss actions ONLY — there is
no `POST /flags` endpoint anywhere in this app. A consuming app writes
`Flag` rows itself (via the ORM), and this stage's own tests create rows
directly the same way (see `tests/test_moderation.py`).

**`target_type`/`target_id` are POLYMORPHIC, deliberately with NO
cross-table FK.** `target_type` is a plain `String(16)` (NOT a DB enum —
the SAME `User.status`/`BlogPost.status`/`Comment.status` precedent: an
app-level closed set of `{"blog_post", "comment", "user"}`,
`app/schemas/moderation.py`'s `FlagTargetType` `StrEnum`, validated at the
request boundary for the `?target_type=` list filter and dispatched on by
`app/api/routers/moderation.py`'s resolve handler — never enforced at the
DB level, since a single `target_id` column can't carry a real FK to three
different tables at once). `target_id` is a bare `Uuid` column — the row it
names is looked up by hand, per `target_type`, at the SERVICE layer
(`app/api/routers/moderation.py`'s `_resolve_target`), not by the database.

`reporter_id` is an OPTIONAL FK to `User`, `ondelete="SET NULL"` — a
consuming app supplies it when the reporting user is known; NULL is a
legitimate, permanent state (an anonymous report, or a reporter whose
account was later deleted) rather than something this table's own FK
constraint should ever block on. This is the ONE FK on this model with an
explicit non-default `ondelete=` — deliberately not RESTRICT/PROTECT like
every other FK in this catalog (`BlogPost.author_id`, `Comment.post_id`/
`author_id`): a flag's own audit value (what was reported, why, and its
resolution) is independent of whether the REPORTER's account still exists,
so losing that one attribution column to a future account deletion is an
acceptable trade against blocking that deletion outright. `resolved_by_id`
(the ACTING ADMIN, set once at resolve/dismiss time) is left at the
catalog's default `ondelete` (RESTRICT) instead — matching `BlogPost.
author_id`'s "don't silently cascade away an audit trail" rationale,
since an admin account is a much rarer, more deliberate deletion than an
end-user reporter's.

`status` is a plain `String(16)`, NOT a DB enum — the `{"open", "resolved",
"dismissed"}` closed set (`app/schemas/moderation.py`'s `FlagStatus`
`StrEnum`), same precedent as every other status column in this catalog.
INDEXED — the admin moderation queue's primary filter
(`app/api/routers/moderation.py`'s `list_admin_flags`) is `?status=open`.
Defaults `"open"` at both the Python/ORM level and the DB level
(`server_default="open"`), the same two-layer shape `BlogPost.status`/
`Comment.status` document."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Flag(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "flags"
    __table_args__ = (
        # The admin queue's own composite filter shape (`?status=&
        # target_type=`, `app/api/routers/moderation.py`'s `list_admin_flags`)
        # — a single composite index covering both columns together, on top
        # of each column's own individual `index=True` below (still useful
        # for a status-only or target_type-only filter query on its own).
        Index("ix_flags_status_target_type", "status", "target_type"),
    )

    # Plain String(16), NOT a DB enum — see module docstring. No cross-table
    # FK on target_id (below) — this column is what a lookup dispatches on.
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Polymorphic, deliberately no ForeignKey — see module docstring.
    target_id: Mapped[uuid.UUID] = mapped_column(SAUuid(as_uuid=True, native_uuid=True), nullable=False, index=True)
    # Optional — a consuming app supplies it; NULL is a legitimate,
    # permanent state (anonymous report, or a reporter account later
    # deleted). ondelete="SET NULL" — see module docstring for why this is
    # the one FK in this catalog that isn't RESTRICT/PROTECT.
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        default=None,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain String(16), NOT a DB enum — see module docstring.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open", index=True
    )
    # The ACTING ADMIN — set once, at resolve/dismiss time. Left at this
    # catalog's default `ondelete` (RESTRICT) — see module docstring.
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=True,
        default=None,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
