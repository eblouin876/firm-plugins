<!--
library: sqlalchemy
versions-covered: "1.4, 2.0"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://docs.sqlalchemy.org
  - https://alembic.sqlalchemy.org
-->

# SQLAlchemy conventions (ORM + Alembic)

Granular guidance for models, sessions, transactions, queries, and migrations. Read after detecting SQLAlchemy. Postgres-engine specifics live in `postgres.md`. Subordinate to the project's existing conventions.

## Version check (do this first)
**SQLAlchemy 1.4 vs 2.0 is decisive** — the query API and ORM style differ.

- **SQLAlchemy 2.0** (modern default): `select()`-style queries executed via `session.execute(select(Model).where(...))`; typed ORM with `DeclarativeBase`, `Mapped[...]` annotations, and `mapped_column()`. Async via `create_async_engine` / `AsyncSession`. The legacy `session.query(...)` API is discouraged.
- **SQLAlchemy 1.4**: the older `session.query(Model).filter(...)` API is common (2.0-style partially available). Match what the project uses.

Confirm the driver: `asyncpg` (async) vs `psycopg`/`psycopg2` (sync) — it must match the engine's sync/async mode.

## Models
- Define ORM models separately from Pydantic schemas (models = storage; schemas = API contract).
- Typed declarative style in 2.0: `Mapped[int]`, `mapped_column(primary_key=True)`, explicit types and nullability.
- Make constraints explicit at the DB level: primary keys, `nullable=False`, `unique=`, foreign keys, check constraints, defaults. The database — not just the app — enforces integrity.
- Define relationships explicitly and choose the loading strategy deliberately (see queries). Set `ondelete`/cascade intentionally. Index columns you filter/join/sort on.

## Sessions & transactions
- One session per request via a dependency (`get_db`) with guaranteed cleanup (yield + close, or an async context manager). Never share a session across requests or use a global session.
- Make transaction boundaries explicit: commit on success, roll back on error. Don't leave a request half-committed.
- In async, use `AsyncSession` and `await` every DB operation. Never block the event loop with a sync DB call on an async path.

## Queries & performance
- **Avoid N+1** — the most common backend perf bug. When accessing a relationship for many rows, eager-load (`selectinload`, `joinedload`) instead of lazy-loading per row.
- Select only what you need; push filtering, sorting, aggregation, and pagination into the query, not into Python after fetching everything.
- Batch inserts/updates rather than looping single-row writes. For slow queries, verify the supporting index exists (`EXPLAIN ANALYZE` — see `postgres.md`).

## Migrations (Alembic)
- Wire up Alembic from day one. Every schema change is a reviewable, reversible migration — never hand-edit a production schema, and don't rely on `Base.metadata.create_all` outside dev/throwaway contexts.
- Generate with autogenerate, then **review and edit** — autogenerate misses server defaults, type/enum changes, and data migrations, and sometimes proposes destructive ops.
- Write a real `downgrade` where feasible. Never edit a migration already applied in shared environments — add a new one.
- Sequence destructive/data changes safely (expand → backfill → contract: add column nullable → backfill → enforce not-null) to avoid downtime and data loss. Migrations run as an explicit deploy step (see the devops deploy conventions).

## Security & integrity
- **Never build SQL by string interpolation.** Use the ORM or parameterized statements exclusively — the primary defense against SQL injection. Flag any raw `text()` with interpolated user input.
- Apply least privilege to the app's DB account. Validate and constrain at the DB level so bad data can't persist even if a bug slips past the API layer. Hash passwords; never store plaintext or reversibly "encrypt" them.
