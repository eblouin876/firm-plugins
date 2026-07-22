<!--
block: components/backend/repository  # catalog component
needs:
  - SQLAlchemy 2.0.x (async extras): the runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row
  - pagination/query.py + pagination/schema.py: sibling modules imported flat (from query import paginate_select; from schema import PageParams, PageResult)
  - a mapped model with an `id` primary-key attribute: AsyncRepository's get()/update()/delete() assume `self.model.id`
exposes:
  - AsyncRepository[ModelT] — get/list/create/update/delete over an AsyncSession, soft-delete-aware by duck-typing; list() returns the INTERNAL PageResult[ModelT], never the wire Page
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# repository

A generic async CRUD repository over SQLAlchemy 2.0: `get`/`list`/
`create`/`update`/`delete` for any mapped model, composing
`pagination/`'s `paginate_select` for `list()` and duck-typing against
`db-mixins/`'s `SoftDeleteMixin` interface for delete/filter behavior —
without importing `mixins.py` directly. Lives at
`templates/components/backend/repository/` in this repo; Stage 3 backend
blocks copy `repository.py` verbatim into `app/core/db/repository.py`.
Canon: `references/backend/sqlalchemy.md`'s "Sessions & transactions" and
"Queries & performance" sections.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block.

**SQLAlchemy-specific — Django cannot reuse this file.** Django's
`QuerySet`/`Manager` is a different abstraction with no
`AsyncRepository[ModelT]` equivalent shipped by this catalog; Stage 4's
Django track does not reuse `repository.py` (a project may hand-build a
similar pattern over `QuerySet` if its own conventions call for it — out
of scope for this component).

## Contents
- Composition contract
- Duck-typed soft-delete, not a hard import
- Wire vs internal: what list() returns
- Commit discipline: this repository never commits
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **SQLAlchemy 2.0.x with the `asyncio` extra** — pinned per
  `references/compatibility-matrix.md`'s Backend — Python row.
- **`pagination/`'s `query.py` and `schema.py`, as flat sibling modules**
  — `repository.py` imports `from query import paginate_select` and `from
  schema import PageParams, PageResult`. Copy all four SQLAlchemy-specific
  files (`mixins.py`, `session.py`, `repository.py`, and pagination's
  `query.py`/`schema.py`) into one `app/core/db/` directory so these flat
  imports resolve.
- **A mapped model with an `id` attribute** — `get()`/`update()` (via the
  caller's own fetched object)/`delete()` assume `self.model.id` is the
  primary key column, matching `db-mixins/`'s `UUIDPrimaryKey` naming. A
  model with a differently-named primary key needs its own repository
  subclass overriding `get()`.

**EXPOSES**
- `AsyncRepository[ModelT]` — constructed as `AsyncRepository(session,
  Model)`. Methods:
  - `get(id_, *, include_deleted=False) -> ModelT | None`
  - `list(*, params: PageParams, include_deleted=False, filters=()) -> PageResult[ModelT]`
  - `create(**values) -> ModelT`
  - `update(obj, **values) -> ModelT`
  - `delete(obj, *, hard=False) -> None`
- Its co-located doc fragment: `docs/fragment.md`.

> **A route MUST map `PageResult.items` to an output schema and construct
> the wire `Page[SchemaOut]` itself (via `Page.create(...)`) — NEVER
> return `list()`'s result directly as a response body.** `list()`
> returns `PageResult[ModelT]`, pagination/schema.py's INTERNAL container
> — its `items` are raw, unmapped ORM instances (relationship loaders,
> non-JSON-able columns). The wire `Page[T]` is a strict Pydantic model
> with no `arbitrary_types_allowed`; it cannot and must not hold those
> raw instances. See "Wire vs internal: what `list()` returns" below.

## Duck-typed soft-delete, not a hard import

`repository.py` never imports `mixins.py`. Every soft-delete-aware method
checks structurally instead:

- `get()`/`list()` call `hasattr(self.model, "not_deleted")` — present
  only on a model composing `SoftDeleteMixin` — and apply that filter
  when `include_deleted=False` (the default).
- `delete()` calls `hasattr(obj, "mark_deleted")` — soft-deletes
  (`obj.mark_deleted()`) when present and `hard=False` (the default);
  otherwise issues a real `DELETE`.

A model that does **not** compose `SoftDeleteMixin` works with
`AsyncRepository` unmodified: `delete()` always hard-deletes, and
`include_deleted` is simply a no-op (there's no `deleted_at` column to
filter on). This keeps `repository.py` and `mixins.py` independently
copyable — a project could in principle use one without the other — while
still composing correctly when both are present, which is the common
case.

## Wire vs internal: what list() returns

`list()` returns `PageResult[ModelT]` — pagination/schema.py's INTERNAL
container (`items`, `total`, `page`, `size`; no `pages`, not a Pydantic
model) — never `Page[ModelT]`. `list()`'s `items` are raw `ModelT` ORM
instances the repository fetched, not yet mapped to any output schema;
`Page[T]` is the app's strict wire model (`extra="forbid"`, no
`arbitrary_types_allowed`) and must never be asked to hold them.

A ROUTE handler is the one place with enough context to do the mapping —
it knows the output schema — so it, not this repository, does:

```python
result = await repo.list(params=params)
mapped = [WidgetOut.model_validate(w) for w in result.items]
return Page.create(mapped, total=result.total, params=params)
```

Returning `list()`'s `PageResult` directly as a response body is a bug,
not a style choice: it risks leaking unmapped ORM columns, a lazy-load
failing outside the request's session, or a field the output schema
deliberately omits. See `pagination/README.md`'s "schema.py: the neutral
contract" and `PageResult`'s docstring in `pagination/schema.py` for the
full rationale behind the split.

## Commit discipline: this repository never commits

Every mutating method (`create`, `update`, `delete`) calls
`session.flush()`, never `session.commit()`. Flushing is what populates
DB-generated values (a `UUIDPrimaryKey`'s default, a `TimestampMixin`'s
`server_default`) on the returned/mutated instance so a caller that
touches the object again within the same request sees consistent state —
but the actual transaction boundary (commit on success, rollback on
exception) belongs to `db-session/`'s `get_db()` dependency, which wraps
the whole request. A repository that committed internally would end the
request's transaction early, breaking `get_db()`'s all-or-nothing
guarantee for a request that calls the repository more than once.

## Testing

`tests/test_repository.py` composes `db-mixins/`'s `Base`,
`UUIDPrimaryKey`, `TimestampMixin`, `SoftDeleteMixin` and
`pagination/`'s `PageParams`/`PageResult` against an in-memory sqlite
engine (aiosqlite) — the real four-file composition a Stage 3
`app/core/db/` directory has. Covers: `create()` populating a generated id
and timestamps, `get()` returning `None` for a missing id and the created
object by id, `get()` excluding/including a soft-deleted row via
`include_deleted`, `update()` mutating and persisting, `delete()`'s soft
path (row stays in the table, `deleted_at` set, confirmed via a raw
query bypassing the repository), `delete(hard=True)` actually removing
the row, a model with **no** `SoftDeleteMixin` always hard-deleting
regardless of `hard=`, `list()`'s pagination math, `list()` returning the
internal `PageResult` (not the wire `Page` — no `pages` field, not a
Pydantic model), `list()` excluding/including soft-deleted rows, `list()`
applying caller-supplied `filters`, and `list()` on a non-soft-deletable
model returning every row.

Run: `uv run --python 3.13 --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with pytest --with pytest-asyncio --with 'pydantic==2.13.*' -- pytest templates/components/backend/repository/tests/ -q`
(`pydantic` is required transitively — `repository.py` imports
`pagination/schema.py`, which is Pydantic-only.)

## Judgment calls

- **Duck-typing over a Protocol or a hard `SoftDeleteMixin` import.** A
  `Protocol` would give static type-checking on the `not_deleted`/
  `mark_deleted` interface, but would still require every model's type
  annotation to satisfy it explicitly; plain `hasattr` checks let
  `repository.py` and `mixins.py` compose or not compose per-model with
  zero import coupling between the two components, matching this
  catalog's "components stitch together, don't hard-depend on each
  other's internals" convention (see the `template-author` skill's core
  rules).
- **`AsyncRepository` assumes an `id` attribute, not a configurable
  primary-key name.** Every model in this kit's own mixins uses `id` (via
  `UUIDPrimaryKey`) — generalizing to an arbitrary PK column name would
  add a parameter every call site has to think about for a case this
  catalog's own conventions don't produce. A project with a genuinely
  different PK name subclasses `AsyncRepository` and overrides `get()`.
- **Never commits.** See "Commit discipline" above — a deliberate
  boundary with `db-session/`'s `get_db()`, not an oversight.
- **`list()` returns `PageResult[ModelT]`, not `Page[ModelT]`.** Before
  this fix, `list()` returned `Page[ModelT]` — the wire model, holding raw
  ORM rows — kept legal only by `arbitrary_types_allowed=True` on `Page`.
  That let a route return `list()`'s result directly as a response body
  with zero schema mapping, leaking ORM internals onto the wire and
  quietly widening the wire contract's `T` to "anything," not just a
  serializable schema. Splitting `PageResult` (internal) from `Page`
  (wire, strict) closes that hole: `list()` physically cannot be returned
  as a response body without a route explicitly mapping it first.
