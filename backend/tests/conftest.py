"""
Global pytest fixtures for the backend test suite.

Fixtures:
- `client` — async HTTP client pointing at the FastAPI app
- `db` — async SQLAlchemy session against the test database
- `apply_migrations` — session-scoped fixture that runs alembic upgrade head

Tests run against docker-compose.test.yml (postgres_test:5433, redis_test:6380).
Environment variables are injected via [tool.pytest.ini_options] env in pyproject.toml.
"""
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.config import get_settings

settings = get_settings()


@pytest.fixture(scope="session")
def apply_migrations() -> None:
    """Run database migrations before tests (session-scoped).
    
    Note: This assumes migrations have already been run.
    In a full test setup, you would run `alembic upgrade head` here.
    """
    # For now, assume migrations are already applied
    # TODO: Add alembic upgrade head in CI/CD setup
    pass


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Async database session for tests.
    
    Creates a new session for each test, with automatic rollback.
    """
    # Create test engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create session factory
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        # Start a transaction
        async with session.begin():
            yield session
            # Rollback after test (cleanup)
            await session.rollback()
    
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound to the FastAPI ASGI app (no network round-trip)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
