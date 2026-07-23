# Vendored from templates/components/backend/pagination/schema.py; keep in sync via the weekly freshness audit.
# Do not hand-edit below this line except for this header — see that component's README
# for the composition contract this file is part of.
# DRIFT: source file also defines `PageResult`, a dataclass container documented there as
# "SQLAlchemy-repository plumbing a Django view has no use for" — dropped here per that
# file's own module docstring ("A Django project (Stage 4) copies schema.py alone — in
# practice, only its PageParams/Page shapes matter there"). The `from dataclasses import
# dataclass` source-file import is dropped along with it since nothing below uses it.
# `PageParams`/`Page` below are otherwise byte-identical to the source.

from __future__ import annotations

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
