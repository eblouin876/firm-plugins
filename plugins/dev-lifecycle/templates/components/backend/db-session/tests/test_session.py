"""Tests for the db-session drop-in (session.py). No real database — an
in-memory sqlite engine via aiosqlite, shared across connections through
StaticPool (the standard pattern for a hermetic async-sqlite test)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

import session as session_mod
from session import configure_engine, get_db, get_engine, get_sessionmaker


class _Base(DeclarativeBase):
    """Self-contained test model — deliberately not importing db-mixins'
    Base, keeping this component's own tests independent of that sibling
    component."""


class Item(_Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest_asyncio.fixture(autouse=True)
async def engine():
    eng = configure_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    yield eng
    await eng.dispose()
    session_mod._reset_engine_for_tests()


# --- configure_engine / accessors -----------------------------------------


def test_get_engine_returns_configured_engine(engine):
    assert get_engine() is engine


def test_get_sessionmaker_returns_configured_sessionmaker(engine):
    assert get_sessionmaker() is not None


def test_get_engine_raises_when_not_configured():
    session_mod._reset_engine_for_tests()
    with pytest.raises(RuntimeError, match="configure_engine"):
        get_engine()


def test_get_sessionmaker_raises_when_not_configured():
    session_mod._reset_engine_for_tests()
    with pytest.raises(RuntimeError, match="configure_engine"):
        get_sessionmaker()


# --- configure_engine: fail-fast on a non-async driver scheme ---------------


def test_configure_engine_rejects_bare_postgresql_scheme():
    with pytest.raises(ValueError, match="asyncpg"):
        configure_engine("postgresql://user:pass@localhost/db")


def test_configure_engine_rejects_bare_sqlite_scheme():
    with pytest.raises(ValueError, match="aiosqlite"):
        configure_engine("sqlite:///test.db")


def test_configure_engine_rejects_bare_mysql_scheme():
    with pytest.raises(ValueError, match="aiomysql"):
        configure_engine("mysql://user:pass@localhost/db")


def test_configure_engine_rejection_message_names_the_offending_url():
    with pytest.raises(ValueError, match=r"postgresql://user:pass@localhost/db"):
        configure_engine("postgresql://user:pass@localhost/db")


def test_configure_engine_rejecting_a_bad_url_does_not_clobber_the_configured_engine(engine):
    # A failed configure_engine() call must not overwrite the
    # already-configured (good) engine/sessionmaker.
    assert get_engine() is engine
    with pytest.raises(ValueError):
        configure_engine("postgresql://user:pass@localhost/db")
    assert get_engine() is engine


def test_configure_engine_accepts_an_already_async_scheme_without_raising(engine):
    # sqlite+aiosqlite:// is what the autouse `engine` fixture already
    # configured -- this asserts it didn't raise (a smoke check that the
    # guard doesn't false-positive on the async scheme itself).
    assert get_engine() is engine


# --- get_db: yields an AsyncSession ----------------------------------------


@pytest.mark.asyncio
async def test_get_db_yields_an_async_session():
    gen = get_db()
    db_session = await gen.__anext__()
    try:
        assert isinstance(db_session, AsyncSession)
    finally:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()


def test_get_db_raises_when_not_configured():
    session_mod._reset_engine_for_tests()
    gen = get_db()
    with pytest.raises(RuntimeError, match="configure_engine"):
        # get_sessionmaker() is called synchronously before the first
        # `yield`, so driving the generator once is enough to raise.
        import asyncio

        asyncio.run(gen.__anext__())


# --- get_db: commit-on-success ----------------------------------------------


@pytest.mark.asyncio
async def test_get_db_commits_on_success():
    gen = get_db()
    db_session = await gen.__anext__()
    db_session.add(Item(name="widget"))
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()  # drives the commit path

    # A fresh session must see the committed row.
    verify_session = get_sessionmaker()()
    async with verify_session:
        rows = (await verify_session.execute(select(Item))).scalars().all()
        assert [r.name for r in rows] == ["widget"]


# --- get_db: rollback-on-exception ------------------------------------------


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception():
    gen = get_db()
    db_session = await gen.__anext__()
    db_session.add(Item(name="should-not-persist"))

    with pytest.raises(RuntimeError, match="boom"):
        await gen.athrow(RuntimeError("boom"))

    verify_session = get_sessionmaker()()
    async with verify_session:
        rows = (await verify_session.execute(select(Item))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_get_db_reraises_the_original_exception():
    gen = get_db()
    await gen.__anext__()

    class _CustomError(Exception):
        pass

    with pytest.raises(_CustomError):
        await gen.athrow(_CustomError("domain error"))


# --- get_db: always closes ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_closes_session_after_success(monkeypatch):
    closed = []
    original_close = AsyncSession.close

    async def spy_close(self):
        closed.append(True)
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", spy_close)

    gen = get_db()
    await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert closed == [True]


@pytest.mark.asyncio
async def test_get_db_closes_session_after_exception(monkeypatch):
    closed = []
    original_close = AsyncSession.close

    async def spy_close(self):
        closed.append(True)
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", spy_close)

    gen = get_db()
    await gen.__anext__()
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))

    assert closed == [True]
