"""Stage 5a (#41): the `User` model the vendored auth component's
`UserStore` protocol is implemented against (see
`app/core/security/auth/stores.py`). Not a vendored file itself — built on
top of the vendored `app/core/db/mixins.py`, same composition pattern as
`app/models/item.py`.

Stage 5c (#45): `email_verified`/`verified_at` back
`_core.UserRecord.email_verified` and `UserStore.mark_email_verified` (see
`app/core/security/auth/stores.py`'s `SqlAlchemyUserStore.
mark_email_verified`) — set once `AccountService.verify_email` successfully
consumes a `"verify"` single-use token for this user. `email_verified`
defaults `False` at the Python/ORM level (every row this app inserts
supplies it explicitly) — Alembic 0003 additionally gives the DB column a
`server_default` of `false` so the migration itself backfills any
pre-existing row without a NULL/undefined value, per that migration's own
docstring.

Stage 13b: `status` backs the admin user-management surface
(`app/api/routers/admin.py`) — an app-level, closed set of
`{"active", "suspended", "banned"}` (`app/schemas/admin.py`'s `UserStatus`
`StrEnum`), stored as a plain `String(16)`, **NOT** a DB-level enum —
matching `roles`'s own JSON-not-`ARRAY` and
`app/models/single_use_token.py`'s `purpose` column precedent: a DB enum
type is a schema-migration event of its own to add/remove a member, and
this app's hermetic sqlite test suite needs a column type sqlite actually
has. Defaults `"active"` at the Python/ORM level, same two-layer
`default`/`server_default` shape `email_verified` above documents — Alembic
0004 gives the DB column a `server_default='active'` so that migration
backfills every pre-existing row to a real, non-NULL `"active"` rather than
leaving it undefined."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    """`email` is stored already-normalized (lowercased/stripped) by
    `_core.AuthService._normalize_email` — this model does not re-normalize
    it, so the unique index below is on exactly the value the auth core
    already normalized, and a raw `SELECT ... WHERE email = :normalized`
    (as `UserStore.get_by_email` issues) matches case-insensitively in
    practice without needing a case-insensitive collation.

    `roles` uses `sa.JSON` (a plain JSON column), not Postgres'
    `ARRAY(String)` — deliberately, even though this table only ever runs
    on Postgres in prod: `ARRAY` has no sqlite equivalent, and this app's
    hermetic test suite (`tests/conftest.py`) runs the identical model
    against aiosqlite — a Postgres-only column type would make `User`
    untestable outside a real Postgres connection, unlike every other
    model/mixin in this catalog (see `app/core/db/mixins.py`'s own
    `UUIDPrimaryKey` docstring on the same cross-dialect-portability
    reasoning for its `Uuid` type choice). JSON stores the same `list[str]`
    shape on both dialects — Postgres' native `json`/`jsonb`-under-the-hood
    column, sqlite's `TEXT`-encoded JSON — with SQLAlchemy handling the
    (de)serialization identically either way. `default=list` (not `[]`) is
    a required — a single shared mutable default would be reused, byte-for-
    byte, across every `User` row's in-Python default, a classic mutable-
    default-argument bug applied to an ORM column default."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
