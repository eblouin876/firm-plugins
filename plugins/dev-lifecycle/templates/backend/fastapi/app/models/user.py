"""Stage 5a (#41): the `User` model the vendored auth component's
`UserStore` protocol is implemented against (see
`app/core/security/auth/stores.py`). Not a vendored file itself — built on
top of the vendored `app/core/db/mixins.py`, same composition pattern as
`app/models/item.py`."""

from __future__ import annotations

from sqlalchemy import JSON, String
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
