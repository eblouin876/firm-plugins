"""Framework-neutral-within-SQLAlchemy model mixins: a UUID primary key that
renders correctly on both sqlite (hermetic tests) and PostgreSQL (prod), a
created/updated timestamp pair, and a soft-delete flag with its query
helper. SQLAlchemy 2.0 typed-declarative style (`Mapped[]`/`mapped_column`)
throughout — pinned per references/compatibility-matrix.md's Backend —
Python row. Canon: references/backend/sqlalchemy.md ("Models" — explicit
DB-level constraints; typed declarative style).

Drop-in: copy this file into app/core/db/mixins.py. SQLAlchemy-specific —
Django models do not use `Mapped[]`/`mapped_column`/`DeclarativeBase` at
all, so a Django backend (Stage 4) does NOT reuse this file; it reaches for
Django's own `models.UUIDField`, `auto_now_add`/`auto_now`, and a custom
soft-delete manager instead. Keep this file alongside session.py and
repository.py (also SQLAlchemy-specific) when copied — repository.py duck-
types against the `not_deleted()`/`mark_deleted()` interface this module
defines rather than importing it directly, so there is no hard import
coupling between them, but a model composing repository.py's soft-delete
behavior needs these mixins present in the same app/core/db/ directory.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.elements import ColumnElement


class Base(DeclarativeBase):
    """The declarative base every model in the app extends. One Base per
    app (SQLAlchemy's metadata/registry is per-Base) — a project with more
    than one database uses more than one Base, not more than one of this
    class body."""


class UUIDPrimaryKey:
    """A `uuid.UUID` primary key using SQLAlchemy's own portable `Uuid`
    type (added in SQLAlchemy 2.0), not a hand-rolled `String(36)` or a
    Postgres-only `postgresql.UUID`. `Uuid`'s defaults (`as_uuid=True`,
    `native_uuid=True`) are exactly what's wanted here and are spelled out
    explicitly rather than left implicit: on sqlite it compiles to
    `CHAR(32)` (32 hex chars, no dashes) — which is what makes this mixin
    usable in hermetic sqlite-backed tests with zero PostgreSQL-specific
    setup — and on PostgreSQL it compiles to the native `UUID` column type,
    not a text column, so indexing and storage stay Postgres-native in
    prod. Same Python-side type (`uuid.UUID`) either way; only the wire
    column type differs per dialect, and SQLAlchemy handles that
    translation, not application code.

    A mixin, not a full model — combine with `Base` and at least one other
    mixin/column set to form a real table:

        class Widget(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
            __tablename__ = "widgets"
            name: Mapped[str] = mapped_column(String(100))
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """`created_at`/`updated_at`, both timezone-aware, but set by two
    genuinely different mechanisms — don't conflate them:

    - `created_at` uses a real DB-level `server_default=func.now()` — the
      database itself supplies the value for ANY INSERT that reaches this
      table, through this ORM or otherwise (a raw-SQL backfill, a
      migration, a different service sharing the table), matching
      references/backend/sqlalchemy.md's "Models" section: "Make
      constraints explicit at the DB level... The database — not just the
      app — enforces integrity."
    - `updated_at` uses SQLAlchemy's `onupdate=func.now()`, which is an
      **ORM-level** convenience, NOT `server_onupdate`: SQLAlchemy only
      adds `updated_at = now()` to the `SET` clause of an `UPDATE` *it
      itself issues* (via a flush on a tracked, dirty instance). A raw-SQL
      `UPDATE`, a migration-time bulk update, or another service writing
      to this table directly will NOT bump `updated_at` — there is no
      database trigger enforcing it, unlike `created_at`'s real
      `server_default`. If cross-path enforcement is required (any
      `UPDATE`, from any source, must bump `updated_at`), add a database
      trigger, or the dialect's `server_onupdate` where it's supported —
      this mixin's `onupdate=` alone does not cover that case."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """A nullable `deleted_at` column plus the query/mutation helpers that
    make "soft delete" a consistent, filterable state rather than an ad
    hoc `is_deleted: bool` a caller has to remember to check everywhere.

    `not_deleted()` returns a SQLAlchemy column expression, not a filtered
    query — compose it into any `select()`:

        stmt = select(Widget).where(Widget.not_deleted())

    `repository.py`'s `AsyncRepository` duck-types against this exact
    method (`hasattr(model, "not_deleted")`) to apply it automatically on
    every `get`/`list`, and against `mark_deleted()` on every `delete()` —
    see that component's README for the composition contract."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @classmethod
    def not_deleted(cls) -> ColumnElement[bool]:
        """The `WHERE` fragment for "not soft-deleted" — `IS NULL`, not
        `== None`, so it compiles to real SQL `IS NULL` rather than a
        Python identity comparison SQLAlchemy has to special-case."""
        return cls.deleted_at.is_(None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_deleted(self, *, when: datetime | None = None) -> None:
        """Sets `deleted_at` in Python (timezone-aware UTC by default) —
        the mutation counterpart to `not_deleted()`'s query side. Does not
        flush/commit; the caller's session-management layer (see
        db-session/) owns that."""
        self.deleted_at = when or datetime.now(timezone.utc)
