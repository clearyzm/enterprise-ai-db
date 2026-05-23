"""Async database session management.

Key responsibilities:
1. Create async engine from DATABASE_URL
2. Provide async_session_maker for dependency injection
3. Inject tenant_id from JWT into PostgreSQL session for RLS enforcement
"""
from collections.abc import AsyncGenerator
from uuid import UUID

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.rls import set_tenant_context
from app.utils.jwt import decode_access_token, extract_bearer_token

logger = structlog.get_logger(__name__)
settings = get_settings()

# Async engine — connection pool managed by SQLAlchemy
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    isolation_level="SERIALIZABLE",
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _extract_tenant_id_from_request(request: Request) -> UUID | None:
    """Extract tenant_id from JWT in Authorization header.
    
    Returns None if:
      - No Authorization header
      - Malformed Bearer token
      - JWT decode fails (invalid signature, expired, etc.)
      - JWT payload missing 'tid' claim
    
    This is fail-closed: any failure → None → RLS placeholder UUID → blocks all rows.
    """
    try:
        authorization = request.headers.get("authorization")
        if not authorization:
            return None
        token = extract_bearer_token(authorization)
        payload = decode_access_token(token)
        tenant_id_str = payload.get("tid")
        if not tenant_id_str:
            return None
        return UUID(tenant_id_str)
    except Exception as e:
        logger.debug("get_db.jwt_extraction_failed", error=str(e), path=request.url.path)
        return None


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session with tenant context set for RLS.
    
    Flow:
      1. Create a new session
      2. Extract tenant_id from JWT (if present)
      3. SET LOCAL app.tenant_id = '<tenant_id>' on the session
      4. Yield session to the route handler
      5. async with block auto-closes session + rollbacks uncommitted txn
    
    This dependency works without relying on BaseHTTPMiddleware (which has
    been observed to skip dispatch on /api/v1/* routes), making it the
    authoritative source of tenant context for RLS.
    """
    async with async_session_maker() as session:
        tenant_id = _extract_tenant_id_from_request(request)
        await set_tenant_context(session, tenant_id)
        logger.debug(
            "get_db.tenant_context_set",
            tenant_id=str(tenant_id) if tenant_id else "none",
            path=request.url.path,
        )
        yield session
