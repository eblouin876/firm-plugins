<!--
library: postgres
versions-covered: "14–17"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://www.postgresql.org/docs
-->

# PostgreSQL conventions

Granular guidance for using Postgres well from the app: native types, indexing, integrity, and connection pooling. Read after detecting Postgres. ORM/query mechanics live in `sqlalchemy.md` (or `django.md` for the Django ORM). Subordinate to the project's existing conventions.

## Native types — use them where they fit
- `timestamptz` for timestamps (store timezone-aware UTC), never a naive `timestamp`.
- `numeric` for money and exact decimals — never `float`.
- `uuid` for surrogate keys where you want non-sequential IDs.
- `jsonb` (not `json`) for semi-structured data, with a **GIN index** when you query into it.
- Native `arrays` and `enum`s where they model the domain cleanly (mind that changing an enum is a migration).

## Indexing
- Add indexes for columns you filter, join, or sort on frequently; unique indexes for natural keys.
- Choose the index type: B-tree (default) for equality/range; GIN for `jsonb`/full-text/arrays; partial indexes for a hot subset (`WHERE active`); composite indexes ordered by selectivity for multi-column predicates.
- Don't over-index — every index costs write throughput and storage. Index to the actual query patterns, verified with `EXPLAIN ANALYZE`, not speculatively.

## Integrity
- Enforce integrity in the **schema**, not only in app code: primary keys, foreign keys (with intentional `ON DELETE` behavior), `NOT NULL`, `UNIQUE`, and `CHECK` constraints. A constraint in the database holds even when a bug slips past the API layer.
- Use transactions for multi-statement invariants so partial writes can't leave inconsistent state.

## Performance
- N+1 and unbounded result sets are the usual culprits (see `sqlalchemy.md`). Paginate list queries; don't `SELECT *` when you need three columns.
- Diagnose with `EXPLAIN (ANALYZE, BUFFERS)`; look for sequential scans on large tables where an index should apply, and for row-estimate mismatches (stale stats → `ANALYZE`).

## Connection pooling
- Pool connections appropriately for the deployment. Postgres connections are relatively expensive; a serverless or high-concurrency app usually needs a pooler (PgBouncer, or the platform's) in transaction mode.
- Be deliberate about pool size with async drivers — too large a pool starves the database; too small serializes requests.

## Operations
- Prefer a **managed** Postgres for anything holding real data (backups, failover, patching) over self-hosting in a container — containers are ephemeral; durable data shouldn't be (see the devops deploy conventions).
- Back up / snapshot before destructive migrations, and have a tested restore path.
