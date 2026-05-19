"""Async database session management.

Key responsibilities:
1. Create async engine from DATABASE_URL
2. Provide async_session_maker for dependency injection
3. Support SET LOCAL app.tenant_id (called by middleware via set_tenant_context)
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

# Async engine — connection pool managed by SQLAlchemy
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,  # Verify connections before use
    pool_size=10,
    max_overflow=20,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Allow access to objects after commit
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes.

    Usage:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            ...

    Phase 2 middleware will call set_tenant_context(session, tenant_id)
    before yielding to ensure RLS is active.
    """
    async with async_session_maker() as session:
        # Phase 2: middleware will inject SET LOCAL app.tenant_id here
        # For now, yield session directly (RLS policies will block if tenant_id not set)
        yield session
