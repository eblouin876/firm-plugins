<!--
block: components/backend/pagination  # catalog component
needs:
  - pydantic v2 (2.13.x): schema.py's sole dependency, pinned per references/compatibility-matrix.md's Backend — Python row
  - SQLAlchemy 2.0.x (async extras): query.py's additional dependency — only needed by the SQLAlchemy half, not by schema.py
exposes:
  - PageParams — request-side page/size params (schema.py, neutral)
  - Page[T] — the STRICT generic {items, total, page, size, pages} wire response envelope, no arbitrary_types_allowed (schema.py, neutral)
  - PageResult[T] — INTERNAL, non-wire container (items, total, page, size; not a Pydantic model) returned by paginate_select/AsyncRepository.list() (schema.py, neutral)
  - paginate_select(session, stmt, params) -> PageResult[Any] — applies limit/offset to a select() and fills a PageResult (query.py, SQLAlchemy-specific)
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# pagination

Two files, deliberately split by reusability, living in one directory:
`schema.py` (framework-neutral, Pydantic v2 only — THE pagination contract
Stage 4's Django track reimplements against) and `query.py` (the
SQLAlchemy-specific half that applies it to a `select()`). Lives at
`templates/components/backend/pagination/` in this repo; Stage 3 backend
blocks copy both files into `app/core/db/pagination/`. A Django project
(Stage 4) copies `schema.py` alone.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block. It's the SQLAlchemy half's
counterpart 4 and the neutral half's counterpart 6 of Stage 3's backend
catalog — one directory, two files, kept **file-distinct** by reusability
rather than split into two directories, since they're always installed
together on the SQLAlchemy side and the neutral file is trivially
copy-alone for a Django project.

## Contents
- Composition contract
- schema.py: the neutral contract (THE shape)
- Wire vs internal: Page vs PageResult
- query.py: applying it to a select()
- Why two round trips, not a window function
- Offset pagination now, cursor pagination later
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **`schema.py`**: Pydantic v2, 2.13.x — its only dependency. **No
  SQLAlchemy import anywhere in this file** — that's the point; Stage 4's
  Django track reuses exactly this file.
- **`query.py`**: SQLAlchemy 2.0.x with the `asyncio` extra, in addition
  to Pydantic (it imports `Page`/`PageParams` from the sibling
  `schema.py`). SQLAlchemy-specific — a Django/DRF pagination class
  reimplements the `Page`/`PageParams` *shape* against a Django
  `QuerySet`, it does not import this file.

**EXPOSES**
- `PageParams` — `page` (1-indexed, `ge=1`), `size` (`ge=1, le=200`), an
  `.offset` property (`(page - 1) * size`, the one place that formula is
  computed), `extra="forbid"`.
- `Page[T]` — the STRICT generic wire response envelope: `items: list[T]`,
  `total`, `page`, `size`, `pages`. No `arbitrary_types_allowed` — `T` is
  always a serializable schema. `Page.create(items, *, total, params)` is
  the one constructor every producer of a `Page` should go through — see
  "schema.py: the neutral contract" below for the exact shape quoted.
- `PageResult[T]` — the INTERNAL, non-wire container: `items: list[T]`,
  `total`, `page`, `size` (no `pages`; a plain `@dataclass`, not a
  Pydantic model). Returned by `paginate_select()` and `repository/`'s
  `AsyncRepository.list()` — see "Wire vs internal" below.
- `paginate_select(session, stmt, params) -> PageResult[Any]` — runs
  `stmt` through the `COUNT(*)` + `LIMIT`/`OFFSET` two-query pattern (see
  "Why two round trips") and returns a filled `PageResult`.
- Its co-located doc fragment: `docs/fragment.md`.

`repository/`'s `AsyncRepository.list()` calls `paginate_select()`
directly (`from query import paginate_select`) — see that component's
README for how the two compose.

## schema.py: the neutral contract (THE shape)

This is the pagination envelope every list endpoint in the app returns,
and the shape Stage 4's Django/DRF track reimplements against even though
it never imports this file:

```python
class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)

class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")
    items: list[T]
    total: int
    page: int
    size: int
    pages: int
```

Serialized: `{"items": [...], "total": 137, "page": 2, "size": 20, "pages": 7}`.
1-indexed `page`, `size` capped at 200 server-side (a client asking for
`size=100000` gets a 422, not an accidental unbounded query — per
`references/backend/fastapi.md`'s "Pagination, filtering, versioning": "don't
return unbounded collections"). `pages` is always present, computed by
`Page.create()` (`ceil(total / size)`, floored at 0 for an empty result),
so no consumer re-derives it inconsistently.

`Page` is a **strict** wire model — `extra="forbid"`, no
`arbitrary_types_allowed`. At the API boundary `T` is always a
serializable Pydantic schema (or a plain JSON-able type); `Page` never
holds a raw SQLAlchemy ORM instance. See "Wire vs internal" next for where
those raw instances actually live before a route maps them.

## Wire vs internal: Page vs PageResult

```python
@dataclass
class PageResult(Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
```

`PageResult` is the INTERNAL container `paginate_select()` (query.py) and
`repository/`'s `AsyncRepository.list()` actually return — not `Page`. Its
`items` are typically raw SQLAlchemy ORM instances: relationship loaders,
non-JSON-able columns, lazy-loaded attributes — exactly what the strict
wire `Page` must never be asked to hold. It's a plain `@dataclass`, not a
Pydantic model — nothing about it is ever meant to be serialized directly.

**A route MUST map `PageResult.items` to an output schema and construct
the wire `Page[SchemaOut]` itself, via `Page.create(...)`, before
returning a response body:**

```python
result: PageResult[Widget] = await repo.list(params=params)
mapped = [WidgetOut.model_validate(w) for w in result.items]
return Page.create(mapped, total=result.total, params=params)
```

Never return a `PageResult` directly as a response body. Before this
split, `paginate_select()`/`AsyncRepository.list()` returned `Page[Any]`
with `arbitrary_types_allowed=True` set on `Page` itself specifically to
tolerate raw ORM rows — which meant `Page`, THE wire contract, was
permissive everywhere, and a route that forgot to map its items would
still "work" (FastAPI would either fail to serialize unpredictably or, if
`T` was left too loose, leak raw ORM state). Splitting `PageResult` out
closes that hole: `Page` is strict again, and only `PageResult` — a type
that visibly can't be the response body — carries unmapped items.

## query.py: applying it to a select()

```python
async def paginate_select(session: AsyncSession, stmt: Select[Any], params: PageParams) -> PageResult[Any]:
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()
    paged_stmt = stmt.limit(params.size).offset(params.offset)
    items = (await session.execute(paged_stmt)).scalars().all()
    return PageResult(items=list(items), total=total, page=params.page, size=params.size)
```

Pass in a `select()` with whatever `WHERE`/`JOIN`/`ORDER BY` the endpoint
needs already applied — `paginate_select` adds only `LIMIT`/`OFFSET` (to
the page-of-rows query) and wraps the whole statement in `COUNT(*)` (for
the total), so a filtered list's `total` reflects the filter, not the
unfiltered table.

## Why two round trips, not a window function

A single query *can* return both a windowed page and an unwindowed total
in one round trip using `COUNT(*) OVER()` — but that's PostgreSQL-specific
syntax with patchy-to-absent sqlite support, and sqlite is this catalog's
hermetic-test target (see `db-mixins/README.md`'s UUID-type rationale for
the same dual-dialect concern). `paginate_select` deliberately runs two
queries — one `COUNT(*)`, one `LIMIT`/`OFFSET` — so it works identically
on both dialects with no per-backend branch. A project on PostgreSQL only,
at a scale where the extra round trip is a measured cost, can swap in the
window-function version; that's a project-level optimization, not this
component's default.

## Offset pagination now, cursor pagination later

`PageParams`/`Page` use offset/page pagination — a conscious default, not
an oversight:

- **Simple.** `page`/`size` is the shape every client and every internal
  consumer already reasons about; no opaque cursor token to generate,
  encode, or explain.
- **DRF parity.** It matches Django REST Framework's own default
  `PageNumberPagination` shape closely enough that Stage 4's Django track
  reimplements the identical `{items, total, page, size, pages}` envelope
  from its own paginator — see this component's module docstring's note
  on Stage 4 conformance.

Known limits, accepted deliberately at this catalog's target scale:

- **Depth cost.** A high page number still costs the database a full
  `OFFSET N` scan to skip N rows before returning the page — cheap at the
  data volumes a typical app starts with, not a promise this stays cheap
  at arbitrary scale.
- **Drift under concurrent inserts.** A row inserted between two page
  requests can shift every later page's window by one, occasionally
  duplicating or skipping a row for a caller paging through a table under
  live, concurrent writes.

Freezing `Page`/`PageParams` now does not foreclose cursor pagination
later: it would ship ADDITIVELY, as a separate `CursorPage`/`CursorParams`
shape living alongside — not replacing — `Page`/`PageParams`. An endpoint
that needs cursor semantics would opt in without any existing
offset-paginated endpoint, or its already-generated API client, changing
shape. No cursor-pagination code exists in this catalog yet; this section
documents the compatibility path, not a currently-exposed class.

## Testing

`tests/test_schema.py` (Pydantic only, no SQLAlchemy) covers: `PageParams`
defaults and its `.offset` math across several page/size combinations,
`page`/`size` bounds rejection (`page <= 0`, `size` out of `[1, 200]`),
`extra="forbid"` rejecting an unknown field, `Page.create()`'s pagination
math (evenly-divisible totals, a remainder, an empty result set, a
single-item result), `Page[T]` working with a plain type and a Pydantic
model, `Page` carrying no `arbitrary_types_allowed` (the MEDIUM-2 fix),
the envelope's serialized key set, `PageResult` holding
items/total/page/size (including an arbitrary non-Pydantic object — the
case `Page` used to accommodate before the split), `PageResult` not being
a Pydantic model, and the documented route-layer pattern of building a
`Page` from a `PageResult` via `Page.create()`.

`tests/test_query.py` (SQLAlchemy, aiosqlite in-memory) covers:
`paginate_select` returning the correct items/total for a first, middle,
and last (partial) page; that it returns the internal `PageResult` (not
`Page` — no `pages` attribute, not a Pydantic model); a page requested
past the end returning empty `items` with `total` still correct; a size
that evenly divides the total; `total` reflecting a `WHERE` filter already
on the passed-in `stmt` (not the whole table); and an empty table.

Run (neutral half only): `uv run --python 3.13 --with 'pydantic==2.13.*' --with pytest -- pytest templates/components/backend/pagination/tests/test_schema.py -q`
Run (both halves together — `query.py` imports `schema.py`): `uv run --python 3.13 --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with pytest --with pytest-asyncio --with 'pydantic==2.13.*' -- pytest templates/components/backend/pagination/tests/ -q`

## Judgment calls

- **One directory, two files, not two directories.** The task split
  pagination into a "SQLAlchemy half" and a "neutral half" by
  *reusability*, not by *deployment unit* — on the SQLAlchemy side the two
  files are always installed together (`query.py` hard-imports `schema.py`
  as a sibling), so a second directory would only add a path to keep in
  sync for zero isolation benefit. A Django project copies `schema.py`
  alone and never touches `query.py` — file-level, not directory-level,
  is where the reusability boundary actually lives.
- **`Page.create()` is the only sanctioned constructor for a real `Page`,
  not documented as a strict runtime requirement.** Nothing stops a
  caller from constructing `Page(...)` directly with a hand-computed
  `pages` value — Pydantic has no mechanism to forbid that without a
  private-constructor pattern this component doesn't adopt (it would
  complicate the common, harmless case of building a `Page` in a test
  fixture). Documented convention, not an enforced one.
- **`paginate_select` always issues two queries, never `COUNT(*) OVER()`.**
  See "Why two round trips" — a deliberate portability choice (sqlite +
  PostgreSQL) over a PostgreSQL-only optimization.
- **`PageResult` is a plain `@dataclass`, not a Pydantic `BaseModel`.**
  Nothing about it is ever serialized directly, so it doesn't need
  Pydantic's validation/serialization machinery — using a dataclass also
  makes it visually and structurally obvious at every call site that this
  is *not* a response model, reinforcing "never return this as a response
  body" beyond just documentation.
- **Offset pagination is the only strategy this catalog ships today.**
  Cursor pagination is deliberately deferred, not rejected — see "Offset
  pagination now, cursor pagination later." Freezing `Page`/`PageParams`
  now is safe specifically because a cursor shape would be additive, not
  a breaking change to this one.
