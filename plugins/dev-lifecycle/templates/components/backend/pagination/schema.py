"""Framework-neutral pagination shapes: request-side page parameters, the
STRICT wire response envelope, and a lightweight INTERNAL container used
only between the data layer and the route layer. Pydantic v2 only (pinned
per references/compatibility-matrix.md's Backend — Python row to Pydantic
v2, 2.13.x) — NO SQLAlchemy import in this file. `PageParams`/`Page` are
one of the two THE-CONTRACT shapes (alongside error-envelope/errors.py)
that Stage 4's Django track reimplements against, not just Stage 3's
FastAPI: a DRF view returns the same `{items, total, page, size, pages}`
shape from its own pagination class, even though it never imports this
file directly. `PageResult` (below) is NOT part of that wire contract —
see its docstring.

Offset/page pagination (`PageParams`/`Page`) is a deliberate default, not
the only pagination strategy this catalog will ever support: it's simple
and matches DRF's own default paginator 1:1 (Stage 4 parity), at the
accepted cost of OFFSET-scan depth cost and result drift under concurrent
inserts at scale. Cursor pagination, if/when needed, ships ADDITIVELY as a
separate `CursorPage`/`CursorParams` shape living alongside — not
replacing — these, so freezing this shape now does not foreclose that
later. See pagination/README.md's "Offset pagination now, cursor
pagination later" for the full rationale; no cursor code exists yet.

Drop-in: copy this file into app/core/pagination/schema.py (or alongside
query.py at app/core/db/pagination/schema.py — either placement works, this
file has no directory-relative imports of its own). The SQLAlchemy-specific
half of pagination lives in this same component's query.py; keep both
together when copying into a SQLAlchemy-backed (Stage 3) project. A Django
project (Stage 4) copies schema.py alone — in practice, only its
`PageParams`/`Page` shapes matter there; `PageResult` is SQLAlchemy-
repository plumbing a Django view has no use for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """Request-side pagination parameters: page/size, 1-indexed. `extra="forbid"`
    so an unrecognized query param (a typo, or an old `offset=`/`limit=`
    caller that hasn't migrated) is a hard 422 instead of being silently
    ignored."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="1-indexed page number.")
    size: int = Field(default=20, ge=1, le=200, description="Items per page (max 200).")

    @property
    def offset(self) -> int:
        """The 0-indexed row offset this page starts at — `(page - 1) *
        size`, computed once here so every consumer (the SQLAlchemy half
        in query.py, a Django queryset slice) uses the identical formula
        rather than each re-deriving it."""
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    """THE generic response envelope for every paginated list endpoint in
    this app: `{items, total, page, size, pages}`. Pydantic v2 generic
    (`Page[WidgetOut]`, `Page[int]`, ...) — FastAPI resolves the concrete
    schema per route from the type parameter, same as any other Pydantic
    generic response model.

    STRICT wire model — deliberately NO `arbitrary_types_allowed`. `T`
    here is always a serializable Pydantic schema (or a plain JSON-able
    type), never a raw SQLAlchemy ORM instance. A route handler is
    responsible for mapping ORM rows to an output schema and constructing
    `Page[SchemaOut]` itself (via `Page.create()`) — a route MUST NOT
    return the internal `PageResult` container (below) as a response
    body. `repository/`'s `AsyncRepository.list()` does NOT return this
    class; it returns `PageResult`, precisely so this wire type never has
    to tolerate a non-serializable `T`."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    pages: int = Field(ge=0)

    @classmethod
    def create(cls, items: Sequence[T], *, total: int, params: PageParams) -> "Page[T]":
        """The one place page-count math happens — `ceil(total / size)`,
        computed without importing `math.ceil` (integer ceiling division:
        `-(-total // size)`), floored at 0 for an empty result set. Every
        producer of a `Page` (a route mapping a `PageResult`'s items
        through an output schema, a Django DRF paginator reimplementing
        this shape) should go through this constructor rather than
        hand-computing `pages` inline."""
        pages = -(-total // params.size) if total else 0
        return cls(items=list(items), total=total, page=params.page, size=params.size, pages=pages)


# ---------------------------------------------------------------------------
# WIRE vs INTERNAL: `Page` above is the strict response body. `PageResult`
# below is internal-only plumbing between the data layer and the route
# layer. A route MUST map `PageResult.items` to an output schema and
# construct `Page[SchemaOut]` itself via `Page.create(...)` — NEVER return
# a `PageResult` directly as a response body.
# ---------------------------------------------------------------------------


@dataclass
class PageResult(Generic[T]):
    """INTERNAL pagination container — deliberately NOT a Pydantic model
    and NOT part of the wire contract. `pagination/query.py`'s
    `paginate_select()` and `repository/repository.py`'s
    `AsyncRepository.list()` return THIS, not `Page`, because at that
    layer `items` are typically raw SQLAlchemy ORM instances
    (relationship loaders, non-JSON-able columns, lazy-loaded attributes)
    — exactly what `Page` (a strict wire model, `extra="forbid"`, no
    `arbitrary_types_allowed`) must never be asked to hold.

    A ROUTE handler MUST map `items` through an output schema and build
    the wire response via `Page.create(mapped_items, total=result.total,
    params=params)` — never return a `PageResult` directly as a response
    body. FastAPI would fail to serialize it against a declared
    `Page[...]` response model anyway (it isn't one), but the deeper
    reason is integrity, not just a type error: returning raw ORM rows
    risks leaking unmapped columns, triggering a lazy-load outside the
    request's session, or exposing a field the output schema deliberately
    omits."""

    items: list[T]
    total: int
    page: int
    size: int
