# Vendored from templates/components/backend/repository; keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: imports adapted to relative for in-app packaging (see block README).

"""A generic async repository over SQLAlchemy 2.0: get/list/create/update/
delete for any mapped model, integrating pagination/ (query.py's
paginate_select) and duck-typing against db-mixins/'s SoftDeleteMixin
interface (not_deleted()/mark_deleted()) rather than importing it. SQLAlchemy
2.0 async, pinned per references/compatibility-matrix.md's Backend — Python
row. Canon: references/backend/sqlalchemy.md ("Sessions & transactions",
"Queries & performance").

Drop-in: copy this file into app/core/db/repository.py, alongside
mixins.py, session.py, and pagination/'s query.py + schema.py — this
module imports the pagination pair as flat sibling modules (`from query
import paginate_select`; `from schema import PageParams, PageResult`), so
all five files land together in one app/core/db/ directory. Keep the whole
backend/ SQLAlchemy-specific set together when copied — see db-mixins/
README.md's note on this same convention.

SQLAlchemy-specific — Django's ORM (QuerySet/Manager) has no equivalent
generic-repository construct built the same way; Stage 4's Django track
does not reuse this file, though a Django project MAY choose to layer a
similar repository pattern over QuerySet by hand if that project's own
conventions call for it (out of scope here).

Deliberately does NOT commit. Per db-session/'s get_db() contract, the
session-per-request dependency owns the commit/rollback/close boundary;
this repository only flushes (to populate DB-generated values like a
UUIDPrimaryKey's default or a TimestampMixin's server_default) so a caller
that touches the object again in the same request sees consistent state,
without prematurely ending the request's transaction.

`list()` returns pagination/schema.py's `PageResult` — an INTERNAL
container, not the wire `Page` — because its `items` are raw `ModelT` ORM
instances, not yet mapped to an output schema. The ROUTE layer (Step 2)
maps those items to an output schema and constructs the wire
`Page[SchemaOut]` via `Page.create(...)`; this repository never does that
mapping itself (it doesn't know the output schema) and never returns a
`Page` for exactly that reason. See pagination/schema.py's `PageResult`
docstring for the full wire-vs-internal split.
"""

from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

# DRIFT from the vendored source (which imports these as flat sibling
# modules, per the docstring above): this app composes app/core/db as a
# real intra-package, so the imports are relative here — see
# app/core/db/__init__.py's docstring and README.md's "Vendored components".
from .query import paginate_select
from .schema import PageParams, PageResult

ModelT = TypeVar("ModelT")


class AsyncRepository(Generic[ModelT]):
    """Generic CRUD + pagination over one mapped model. Not itself a
    SQLAlchemy declarative class — wraps an `AsyncSession` and a model
    class, and every method is a thin, explicit query built from
    `select()`, matching references/backend/sqlalchemy.md's "Queries &
    performance" (push filtering/pagination into the query, avoid N+1).

    Soft-delete awareness is duck-typed, not a hard import of
    `SoftDeleteMixin`: every method checks `hasattr(self.model,
    "not_deleted")` / `hasattr(obj, "mark_deleted")` before relying on
    them, so `AsyncRepository` works unmodified for a model that does NOT
    compose `SoftDeleteMixin` (in which case `delete()` always hard-
    deletes, and `include_deleted` has no effect since there is no
    `deleted_at` column to filter on)."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def _base_select(self, *, include_deleted: bool):
        stmt = select(self.model)
        if not include_deleted and hasattr(self.model, "not_deleted"):
            stmt = stmt.where(self.model.not_deleted())
        return stmt

    async def get(self, id_: Any, *, include_deleted: bool = False) -> ModelT | None:
        """Fetch by primary key (`self.model.id`). Soft-deleted rows are
        excluded by default — pass `include_deleted=True` to see them
        (e.g. an admin "restore" view)."""
        stmt = self._base_select(include_deleted=include_deleted).where(self.model.id == id_)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        params: PageParams,
        include_deleted: bool = False,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> PageResult[ModelT]:
        """Paginated list, delegating the actual `LIMIT`/`OFFSET` + count
        work to `pagination/query.py`'s `paginate_select` — this method's
        only job is building the right `select()` (soft-delete filter,
        any caller-supplied `filters`) before handing it off.

        Returns the INTERNAL `PageResult[ModelT]` container, NOT the wire
        `Page[ModelT]` — its `items` are raw, unmapped ORM instances. A
        route MUST map them to an output schema and build
        `Page.create(mapped_items, total=result.total, params=params)`
        itself before returning a response body; never return this
        method's result directly as a response."""
        stmt = self._base_select(include_deleted=include_deleted)
        for condition in filters:
            stmt = stmt.where(condition)
        return await paginate_select(self.session, stmt, params)

    async def create(self, **values: Any) -> ModelT:
        """Constructs `self.model(**values)`, adds it to the session, and
        flushes (not commits) so DB-generated values — a
        `UUIDPrimaryKey`'s default, a `TimestampMixin`'s
        `server_default` — are populated on the returned instance."""
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **values: Any) -> ModelT:
        """Mutates `obj`'s attributes in place and flushes — the caller
        already has `obj` (typically from a prior `get()`), so this
        doesn't re-fetch it."""
        for key, value in values.items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT, *, hard: bool = False) -> None:
        """Soft-deletes via `obj.mark_deleted()` when the model composes
        `SoftDeleteMixin` (detected via `hasattr`) and `hard=False` (the
        default). Otherwise — no `SoftDeleteMixin`, or `hard=True`
        explicitly requested — issues a real `DELETE` via
        `session.delete(obj)`. Flushes either way; does not commit (see
        module docstring)."""
        if not hard and hasattr(obj, "mark_deleted"):
            obj.mark_deleted()
        else:
            await self.session.delete(obj)
        await self.session.flush()
