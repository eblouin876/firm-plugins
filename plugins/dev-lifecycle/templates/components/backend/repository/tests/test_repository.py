"""Tests for the repository drop-in (repository.py), composed with its
sibling db-mixins/ (mixins.py) and pagination/ (query.py, schema.py)
components against an in-memory sqlite engine via aiosqlite — the real
composition a Stage 3 app/core/db/ directory has once all four files are
copied in together."""

from __future__ import annotations

import pytest
import pytest_asyncio
from mixins import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey
from schema import PageParams, PageResult
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from repository import AsyncRepository


class Widget(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column(String(100))


class PlainItem(Base, UUIDPrimaryKey, TimestampMixin):
    """Deliberately does NOT compose SoftDeleteMixin -- exercises the
    duck-typed fallback (always hard-deletes, include_deleted is a
    no-op)."""

    __tablename__ = "plain_items"

    name: Mapped[str] = mapped_column(String(100))


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s

    await engine.dispose()


@pytest.fixture()
def widget_repo(session):
    return AsyncRepository(session, Widget)


@pytest.fixture()
def plain_repo(session):
    return AsyncRepository(session, PlainItem)


# --- create -------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_object_with_generated_id_and_timestamps(widget_repo):
    widget = await widget_repo.create(name="gadget")

    assert widget.id is not None
    assert widget.created_at is not None
    assert widget.updated_at is not None
    assert widget.name == "gadget"
    assert widget.deleted_at is None


# --- get ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_id(widget_repo):
    import uuid

    result = await widget_repo.get(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_created_object_by_id(widget_repo):
    widget = await widget_repo.create(name="gadget")

    fetched = await widget_repo.get(widget.id)

    assert fetched is not None
    assert fetched.id == widget.id
    assert fetched.name == "gadget"


@pytest.mark.asyncio
async def test_get_excludes_soft_deleted_by_default(widget_repo):
    widget = await widget_repo.create(name="gadget")
    await widget_repo.delete(widget)

    assert await widget_repo.get(widget.id) is None


@pytest.mark.asyncio
async def test_get_includes_soft_deleted_when_requested(widget_repo):
    widget = await widget_repo.create(name="gadget")
    await widget_repo.delete(widget)

    fetched = await widget_repo.get(widget.id, include_deleted=True)

    assert fetched is not None
    assert fetched.is_deleted is True


# --- update -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_mutates_and_persists(widget_repo):
    widget = await widget_repo.create(name="gadget")
    original_updated_at = widget.updated_at

    updated = await widget_repo.update(widget, name="renamed-gadget")

    assert updated.name == "renamed-gadget"
    assert updated.updated_at >= original_updated_at

    fetched = await widget_repo.get(widget.id)
    assert fetched.name == "renamed-gadget"


# --- delete: soft vs. hard ---------------------------------------------------


@pytest.mark.asyncio
async def test_delete_soft_marks_deleted_at_row_stays_in_table(widget_repo, session):
    widget = await widget_repo.create(name="gadget")

    await widget_repo.delete(widget)

    assert widget.deleted_at is not None
    # The row is still physically present -- confirmable only by bypassing
    # the not_deleted() filter (include_deleted=True), or a raw query.
    raw = (await session.execute(select(Widget).where(Widget.id == widget.id))).scalar_one_or_none()
    assert raw is not None


@pytest.mark.asyncio
async def test_delete_hard_true_removes_the_row(widget_repo, session):
    widget = await widget_repo.create(name="gadget")
    widget_id = widget.id

    await widget_repo.delete(widget, hard=True)

    raw = (await session.execute(select(Widget).where(Widget.id == widget_id))).scalar_one_or_none()
    assert raw is None


@pytest.mark.asyncio
async def test_delete_on_model_without_soft_delete_mixin_always_hard_deletes(plain_repo, session):
    item = await plain_repo.create(name="plain")
    item_id = item.id

    await plain_repo.delete(item)  # hard=False, but PlainItem has no mark_deleted

    raw = (await session.execute(select(PlainItem).where(PlainItem.id == item_id))).scalar_one_or_none()
    assert raw is None


# --- list: pagination + soft-delete filtering + extra filters --------------


@pytest.mark.asyncio
async def test_list_returns_paginated_page_result(widget_repo):
    for i in range(5):
        await widget_repo.create(name=f"widget-{i}")

    result = await widget_repo.list(params=PageParams(page=1, size=2))

    assert len(result.items) == 2
    assert result.total == 5
    assert result.page == 1
    assert result.size == 2


@pytest.mark.asyncio
async def test_list_returns_the_internal_page_result_not_the_wire_page(widget_repo):
    # MEDIUM-2: AsyncRepository.list() must never return the wire Page of
    # raw ORM objects -- it returns PageResult, which the route layer maps
    # into Page[SchemaOut].
    await widget_repo.create(name="gadget")

    result = await widget_repo.list(params=PageParams(page=1, size=20))

    assert isinstance(result, PageResult)
    assert not hasattr(result, "pages")
    assert not hasattr(result, "model_dump")


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted_by_default(widget_repo):
    keep = await widget_repo.create(name="keep")
    drop = await widget_repo.create(name="drop")
    await widget_repo.delete(drop)

    result = await widget_repo.list(params=PageParams(page=1, size=20))

    assert [w.name for w in result.items] == ["keep"]
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_includes_soft_deleted_when_requested(widget_repo):
    keep = await widget_repo.create(name="keep")
    drop = await widget_repo.create(name="drop")
    await widget_repo.delete(drop)

    result = await widget_repo.list(params=PageParams(page=1, size=20), include_deleted=True)

    assert result.total == 2
    assert {w.name for w in result.items} == {"keep", "drop"}


@pytest.mark.asyncio
async def test_list_applies_extra_filters(widget_repo):
    await widget_repo.create(name="alpha")
    await widget_repo.create(name="beta")
    await widget_repo.create(name="gamma")

    result = await widget_repo.list(
        params=PageParams(page=1, size=20),
        filters=[Widget.name.in_(["alpha", "gamma"])],
    )

    assert {w.name for w in result.items} == {"alpha", "gamma"}
    assert result.total == 2


@pytest.mark.asyncio
async def test_list_on_model_without_soft_delete_mixin_returns_all_rows(plain_repo):
    await plain_repo.create(name="one")
    await plain_repo.create(name="two")

    result = await plain_repo.list(params=PageParams(page=1, size=20))

    assert result.total == 2
