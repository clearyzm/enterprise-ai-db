"""Tenant context middleware — sets PostgreSQL session variable for RLS.

Extracts tenant_id from JWT and calls set_tenant_context() before each request.
This ensures RLS policies filter all queries by tenant_id automatically.
"""
from typing import Any
from uuid import UUID

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.rls import set_tenant_context
from app.db.session import async_session_maker
from app.utils.jwt import decode_access_token, extract_bearer_token

logger = structlog.get_logger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware to set tenant context for RLS enforcement.
    
    Flow:
    1. Extract JWT from Authorization header
    2. Decode JWT and extract tenant_id (tid claim)
    3. Create database session
    4. Call set_tenant_context(session, tenant_id)
    5. Store session in request.state for route handlers
    6. Execute request
    7. Close session
    
    If JWT is missing or invalid, set tenant_id to None (zero UUID),
    which causes RLS to block all rows (defense in depth).
    
    Routes that don't require authentication (e.g., /auth/login) will
    have tenant_id set to zero UUID, which is safe because they don't
    query tenant-scoped tables.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request and set tenant context.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler
        
        Returns:
            Response from downstream handler
        """
        tenant_id: UUID | None = None
        
        # Try to extract tenant_id from JWT
        try:
            authorization = request.headers.get("authorization")
            if authorization:
                token = extract_bearer_token(authorization)
                payload = decode_access_token(token)
                tenant_id_str = payload.get("tid")
                if tenant_id_str:
                    tenant_id = UUID(tenant_id_str)
        except Exception as e:
            # Log but don't fail — unauthenticated requests are allowed
            # (e.g., /auth/login, /health). RLS will block tenant-scoped queries.
            logger.debug(
                "tenant_middleware.jwt_extraction_failed",
                error=str(e),
                path=request.url.path,
            )
        
        # Create database session and set tenant context
        async with async_session_maker() as session:
            # Set tenant context (None → zero UUID, blocks all rows)
            await set_tenant_context(session, tenant_id)
            
            # Store session in request state for route handlers
            request.state.db = session
            request.state.tenant_id = tenant_id
            
            # Log tenant context for debugging
            logger.debug(
                "tenant_middleware.context_set",
                tenant_id=str(tenant_id) if tenant_id else "none",
                path=request.url.path,
                method=request.method,
            )
            
            # Execute request
            response = await call_next(request)
            
            return response
