"""The SQLAlchemy-specific half of pagination: applies a `PageParams`
(from the neutral schema.py in this same directory) to a `select()`
statement and returns a filled `PageResult` — the INTERNAL container, not
the wire `Page`. SQLAlchemy 2.0 async, pinned per
references/compatibility-matrix.md's Backend — Python row.

Drop-in: copy this file into app/core/db/pagination/query.py, alongside
schema.py (also in this directory) — this module imports it as a flat
sibling module (`from schema import PageParams, PageResult`), matching how
the rest of the backend/ catalog composes (see db-mixins/README.md's note
on keeping the SQLAlchemy-specific files together). SQLAlchemy-specific —
Django cannot reuse this file (a DRF/Django paginator slices a QuerySet,
not a SQLAlchemy `select()`); Stage 4's Django track reuses only
schema.py's `Page`/`PageParams` wire shape, reimplemented against a DRF
paginator, not this module.

`paginate_select` returns `PageResult`, NOT `Page` — its `items` are
whatever `stmt` selects, typically raw ORM instances. The caller (directly,
or via `repository/`'s `AsyncRepository.list()`) is responsible for
mapping those items to an output schema and constructing the wire
`Page[SchemaOut]` via `Page.create(...)` before it ever becomes a response
body. See schema.py's `PageResult`/`Page` docstrings for the full
wire-vs-internal rationale.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schema import PageParams, PageResult

RowT = TypeVar("RowT")


async def paginate_select(session: AsyncSession, stmt: Select[Any], params: PageParams) -> PageResult[Any]:
    """Runs `stmt` twice: once wrapped in `COUNT(*)` (via `.subquery()`,
    so any `WHERE`/`JOIN` already on `stmt` is honored by the count too —
    a filtered list's `total` reflects the filter, not the whole table),
    and once with `.limit(size).offset(offset)` applied for the page of
    rows actually returned. Two round trips, not one — a single query
    can't return both a windowed page and an unwindowed total in portable
    SQL without a window function this module deliberately avoids for
    sqlite compatibility (the hermetic-test target); a project on
    PostgreSQL only, at a scale where the extra round trip matters, can
    swap in `COUNT(*) OVER()` instead.

    `params.offset` (the `PageParams` property) is the single source of
    truth for the offset math, not re-derived here. Returns the INTERNAL
    `PageResult` container, not the wire `Page` — the caller maps `items`
    to an output schema and builds `Page.create(...)` itself."""
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    paged_stmt = stmt.limit(params.size).offset(params.offset)
    items = (await session.execute(paged_stmt)).scalars().all()

    return PageResult(items=list(items), total=total, page=params.page, size=params.size)
