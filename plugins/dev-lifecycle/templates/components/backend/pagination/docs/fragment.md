<!-- fragment: block:components/backend/pagination -->

## Setup
Copy `schema.py` into `app/core/db/pagination/schema.py`. On the
SQLAlchemy side, also copy `query.py` into the same directory (it imports
`schema.py` as a flat sibling module). A Django project (Stage 4) copies
`schema.py` alone and reimplements the `{items, total, page, size, pages}`
shape against its own DRF paginator (it has no use for `PageResult`, which
is SQLAlchemy-repository-only plumbing).

`paginate_select()` and `AsyncRepository.list()` (repository/) return
`PageResult`, the INTERNAL container — a route MUST map its `items` to an
output schema and build the wire `Page[SchemaOut]` itself via
`Page.create(...)`; never return `PageResult` as a response body.

## Maintenance
`query.py` is SQLAlchemy-specific; `schema.py` is the framework-neutral
contract both Stage 3 (FastAPI) and Stage 4 (Django) conform to (Django
reuses `PageParams`/`Page` only). Offset/page pagination is the current
default; a `CursorPage`/`CursorParams` shape would ship additively later,
not as a breaking change to this one — see the README.
