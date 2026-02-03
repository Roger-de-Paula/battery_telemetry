"""Pytest fixtures. Use test DB (SQLite) and override get_session for tests that need it."""
import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from database import get_session
from main import app
from models import Base

# Use SQLite in-memory so schema is always created from current models (no stale file)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Module-level engine/sessionmaker created once
_test_engine = None
_test_sessionmaker = None


def _get_test_engine():
    global _test_engine
    if _test_engine is None:
        _test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

        async def init():
            async with _test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init())
    return _test_engine


def _get_test_sessionmaker():
    global _test_sessionmaker
    if _test_sessionmaker is None:
        _test_sessionmaker = async_sessionmaker(
            _get_test_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _test_sessionmaker


async def _truncate_tables(engine):
    """Remove all data from tables (for test isolation)."""
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))


def _override_get_session(session_factory):
    """Return an async generator that yields a session from the given factory."""

    async def override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    return override


@pytest.fixture
def client():
    """HTTP client with test DB: tables truncated before each test, get_session overridden."""
    engine = _get_test_engine()
    sm = _get_test_sessionmaker()
    asyncio.run(_truncate_tables(engine))
    app.dependency_overrides[get_session] = _override_get_session(sm)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
