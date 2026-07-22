<!--
block: components/backend/db-mixins  # catalog component
needs:
  - SQLAlchemy 2.0.x: the sole runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row; typed declarative style (Mapped[]/mapped_column)
exposes:
  - Base — the app's DeclarativeBase every model extends
  - UUIDPrimaryKey — a uuid.UUID primary-key mixin using SQLAlchemy's portable Uuid type
  - TimestampMixin — created_at/updated_at, both DB-server-set
  - SoftDeleteMixin — deleted_at + not_deleted()/mark_deleted()/is_deleted
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# db-mixins

A framework-neutral-*within-SQLAlchemy* drop-in `mixins.py`: a `Base`
declarative class plus three composable model mixins — a UUID primary key,
created/updated timestamps, and soft delete. Lives at
`templates/components/backend/db-mixins/` in this repo; Stage 3 backend
blocks copy `mixins.py` verbatim into `app/core/db/mixins.py`. Embodies
`references/backend/sqlalchemy.md`'s "Models" guidance (typed declarative
style, DB-level integrity).

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block.

**SQLAlchemy-specific — Django cannot reuse this file.** `Mapped[]`,
`mapped_column()`, and `DeclarativeBase` are SQLAlchemy 2.0 ORM constructs
with no Django equivalent; Stage 4's Django track reaches for
`models.UUIDField(default=uuid.uuid4)`, `auto_now_add=True`/`auto_now=True`,
and its own soft-delete manager/queryset instead. Only this kit's
framework-*neutral* components (`error-envelope/`, `pagination/schema.py`,
`settings/`) are shared shape across Stage 3 and Stage 4.

## Contents
- Composition contract
- The UUID primary key: sqlite AND PostgreSQL, hermetically
- TimestampMixin: the database sets the clock
- SoftDeleteMixin: a filterable state, not a scattered boolean
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **SQLAlchemy 2.0.x** — the sole runtime dependency, pinned per
  `references/compatibility-matrix.md`'s Backend — Python row. This
  component writes only the 2.0 typed-declarative style
  (`Mapped[]`/`mapped_column()`); it does not run against SQLAlchemy 1.4's
  legacy declarative style.

**EXPOSES**
- `Base` — the `DeclarativeBase` subclass every model in the app extends.
  One per app; a multi-database project defines more than one.
- `UUIDPrimaryKey` — an `id: Mapped[uuid.UUID]` primary-key mixin, backed
  by SQLAlchemy's own `Uuid` type (not a hand-rolled `String(36)` or a
  Postgres-only `postgresql.UUID`).
- `TimestampMixin` — `created_at`/`updated_at`, both timezone-aware and set
  at the database layer (`server_default`/`onupdate` via `func.now()`).
- `SoftDeleteMixin` — a nullable `deleted_at` column, the
  `not_deleted()` classmethod (a composable `WHERE` fragment for
  `select()`), the `is_deleted` property, and `mark_deleted()`.
- Its co-located doc fragment: `docs/fragment.md`.

`repository/`'s `AsyncRepository` duck-types against `not_deleted()` and
`mark_deleted()` (`hasattr` checks) rather than importing this module
directly — see that component's README for the composition contract this
enables. Keep this file alongside `session.py` and `repository.py` (also
SQLAlchemy-specific) in the same `app/core/db/` directory when copied in.

## The UUID primary key: sqlite AND PostgreSQL, hermetically

`UUIDPrimaryKey` uses `sqlalchemy.Uuid(as_uuid=True, native_uuid=True)` —
SQLAlchemy's own portable UUID type (added in 2.0), not a hand-rolled
`String(36)` column or a Postgres-only `postgresql.UUID`. The same Python
type (`uuid.UUID`) round-trips on both backends; only the wire column type
differs, and SQLAlchemy's dialect layer handles that translation:

| Dialect | Compiles to |
| --- | --- |
| sqlite | `CHAR(32)` (32 hex chars, no dashes) |
| PostgreSQL | native `UUID` |

This is precisely what makes the mixin usable in **hermetic sqlite-backed
tests** with zero PostgreSQL-specific setup (no test-container, no real
Postgres instance) while still storing a real, indexable, native `UUID`
column in prod — a `String(36)` mixin would work on both but store a plain
text column in Postgres; a `postgresql.UUID`-typed mixin would work in prod
but fail outright against sqlite. `Uuid`'s constructor arguments are
already SQLAlchemy 2.0's defaults; they're spelled out explicitly in this
module rather than left implicit, so the dual-rendering behavior is
visible at the definition site, not just "whatever the library happens to
default to today."

## TimestampMixin: created_at is DB-level, updated_at is ORM-level

`created_at`/`updated_at` are both timezone-aware (`DateTime(timezone=True)`)
and `nullable=False`, but they are set by two genuinely different
mechanisms — this distinction matters, don't conflate them:

- **`created_at`** uses a real `server_default=func.now()` — a SQL-level
  default the database itself evaluates at INSERT time, not application
  code computing `datetime.now()` beforehand. Per
  `references/backend/sqlalchemy.md`'s "Models" section ("Make
  constraints explicit at the DB level... The database — not just the
  app — enforces integrity"): a row inserted by ANY path (a
  migration-time backfill, a different service sharing the table, a raw
  SQL script) still gets a correct `created_at`, even if it never goes
  through this app's ORM layer at all.
- **`updated_at`** uses `onupdate=func.now()` — an **ORM-level**
  convenience, NOT `server_onupdate`. SQLAlchemy adds `updated_at =
  now()` to the `SET` clause only of an `UPDATE` statement *it itself
  issues* (a flush on a dirty, tracked instance). A raw-SQL `UPDATE`, a
  migration-time bulk update, or another service writing to this table
  directly will **not** bump `updated_at` — there's no database trigger
  behind it the way there is for `created_at`. A project that needs
  `updated_at` bumped regardless of write path needs a real database
  trigger (or the dialect's `server_onupdate`, where supported) — this
  mixin's `onupdate=` alone doesn't cover that case.

## SoftDeleteMixin: a filterable state, not a scattered boolean

`not_deleted()` returns a SQLAlchemy column expression
(`cls.deleted_at.is_(None)`), meant to compose into any `select()`:

```python
stmt = select(Widget).where(Widget.not_deleted())
```

`is_(None)` deliberately, not `== None` — it compiles to real SQL `IS
NULL` instead of a Python-level identity comparison SQLAlchemy has to
special-case. `mark_deleted(*, when=None)` sets `deleted_at` in Python
(UTC by default) without flushing or committing — that discipline belongs
to the session-management layer (`db-session/`), not this mixin.

## Testing

`tests/test_mixins.py` covers: `UUIDPrimaryKey` compiling to `CHAR(32)` on
sqlite and native `UUID` on PostgreSQL (via each dialect's own
`type.compile()`, no live PostgreSQL connection needed), a real UUID
generated on insert against an in-memory sqlite engine, `TimestampMixin`'s
columns being present/non-nullable and actually populated by the database
on insert and bumped on update, `SoftDeleteMixin`'s `not_deleted()`
filtering a mixed set of soft-deleted and active rows correctly, and
`mark_deleted()` both with its default UTC timestamp and an explicit one.

Run: `uv run --python 3.13 --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with pytest --with pytest-asyncio -- pytest templates/components/backend/db-mixins/tests/ -q`
(`aiosqlite`/`pytest-asyncio` are part of the firm-wide SQLAlchemy
verification invocation for consistency across the backend/ components;
this component's own tests are synchronous — `mixins.py` has no async
code — but this keeps one verification command across the SQLAlchemy
half of the catalog.)

## Judgment calls

- **`Uuid(as_uuid=True, native_uuid=True)` spelled out explicitly even
  though both are SQLAlchemy 2.0's defaults.** Leaving them implicit would
  make the dual-sqlite/PostgreSQL-rendering behavior this mixin exists for
  invisible at the definition site — a reader (or a future SQLAlchemy
  default change) shouldn't have to know the library's current defaults to
  know what this column does.
- **No `String(36)` fallback documented.** Some teams hand-roll a
  `String(36)` UUID column for maximum portability to non-SQLAlchemy
  tooling that reads the schema directly. This mixin deliberately doesn't
  offer that as an option — `Uuid` already gets both target dialects
  (sqlite for tests, PostgreSQL for prod) right, and a text-typed UUID
  column loses native indexing/storage benefits in Postgres for no
  compensating benefit at this kit's two supported dialects.
- **`TimestampMixin` has no `updated_at` value on `INSERT` distinct from
  `created_at`.** Both default to the same `func.now()` call at insert
  time (SQLAlchemy evaluates `server_default` once per column, not shared
  across columns) — this is correct: a freshly created row's "last
  updated" time is its creation time.
