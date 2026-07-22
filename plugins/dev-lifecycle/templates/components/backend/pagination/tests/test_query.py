"""Tests for the SQLAlchemy-specific pagination helper (query.py), against
an in-memory sqlite engine via aiosqlite. Self-contained test model —
deliberately not importing db-mixins, keeping this component's own tests
independent of that sibling component."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from query import paginate_select
from schema import PageParams, PageResult


class _Base(DeclarativeBase):
    pass


class Item(_Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as s:
        s.add_all([Item(name=f"item-{i}") for i in range(5)])
        await s.commit()
        yield s

    await engine.dispose()


# --- pagination math against real rows ------------------------------------


@pytest.mark.asyncio
async def test_paginate_select_first_page(session):
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=1, size=2))

    assert [i.name for i in result.items] == ["item-0", "item-1"]
    assert result.total == 5
    assert result.page == 1
    assert result.size == 2


@pytest.mark.asyncio
async def test_paginate_select_returns_the_internal_page_result_not_a_page(session):
    # MEDIUM-2: paginate_select returns PageResult (internal), never the
    # strict wire Page -- it has no `pages` field and is not a Pydantic
    # model.
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=1, size=2))

    assert isinstance(result, PageResult)
    assert not hasattr(result, "pages")
    assert not hasattr(result, "model_dump")


@pytest.mark.asyncio
async def test_paginate_select_middle_page(session):
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=2, size=2))

    assert [i.name for i in result.items] == ["item-2", "item-3"]


@pytest.mark.asyncio
async def test_paginate_select_last_partial_page(session):
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=3, size=2))

    assert [i.name for i in result.items] == ["item-4"]
    assert result.total == 5


@pytest.mark.asyncio
async def test_paginate_select_page_past_the_end_returns_empty_items(session):
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=10, size=2))

    assert result.items == []
    assert result.total == 5  # total reflects the whole (filtered) set, not the empty page


@pytest.mark.asyncio
async def test_paginate_select_size_evenly_divides_total(session):
    stmt = select(Item).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=1, size=5))

    assert len(result.items) == 5
    assert result.total == 5


# --- total reflects filters already on the statement -----------------------


@pytest.mark.asyncio
async def test_paginate_select_total_reflects_where_filter(session):
    stmt = select(Item).where(Item.name.in_(["item-0", "item-1", "item-2"])).order_by(Item.id)
    result = await paginate_select(session, stmt, PageParams(page=1, size=2))

    assert result.total == 3  # not 5 -- the WHERE clause narrows the count too
    assert len(result.items) == 2


# --- empty table -------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginate_select_empty_table():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as s:
        stmt = select(Item)
        result = await paginate_select(s, stmt, PageParams(page=1, size=20))

        assert result.items == []
        assert result.total == 0

    await engine.dispose()
