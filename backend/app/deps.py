"""Dependency injection functions for FastAPI routes.

Provides:
- get_current_user: Extract and validate user from JWT
- require_perm: Permission check decorator
- get_db: Database session (re-exported from session.py)
"""
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.utils.errors import AuthenticationError, PermissionDeniedError, TokenInvalidError
from app.utils.jwt import decode_access_token, extract_bearer_token

settings = get_settings()


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate current user from JWT access token.
    
    Dependency for routes that require authentication.
    
    Args:
        authorization: Authorization header (Bearer <token>)
        db: Database session
    
    Returns:
        Authenticated User object
    
    Raises:
        TokenInvalidError: Missing or malformed token
        AuthenticationError: User not found or inactive
    
    Usage:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return {"email": user.email}
    """
    # Extract token from Authorization header
    token = extract_bearer_token(authorization)
    
    # Decode and validate JWT
    payload = decode_access_token(token)
    
    # Extract user_id from claims
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise TokenInvalidError()
    
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise TokenInvalidError()
    
    # Load user from database
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise AuthenticationError("User not found")
    
    # Check user status
    if user.status != "active":
        raise AuthenticationError("User account is not active")
    
    return user


def require_perm(action: str, resource_type: str) -> Any:
    """Dependency factory for permission checks.
    
    Creates a dependency that checks if current user has specified permission.
    For tenant_admin users, always returns True (bypass).
    
    Args:
        action: Permission action (read/write/delete/approve/manage/ai_query)
        resource_type: Resource type (user/role/department/dataset/record/workflow/audit_log)
    
    Returns:
        FastAPI dependency function
    
    Raises:
        PermissionDeniedError: User lacks required permission
    
    Usage:
        @router.post("/users", dependencies=[Depends(require_perm("write", "user"))])
        async def create_user(...):
            ...
    
    Note:
        This is a simplified version for Phase 2. Full scope-based permission
        checking (department/dataset filtering) will be implemented in
        PermissionService.check() and used in Phase 3+.
    """
    async def _check_permission(user: User = Depends(get_current_user)) -> User:
        # Tenant admins bypass all permission checks
        if user.is_tenant_admin:
            return user
        
        # Load user roles and permissions
        # For Phase 2, we do a simple check: does user have ANY role with this permission?
        has_permission = False
        
        for user_role in user.user_roles:
            role = user_role.role
            for permission in role.permissions:
                if permission.action == action and permission.resource_type == resource_type:
                    has_permission = True
                    break
            if has_permission:
                break
        
        if not has_permission:
            raise PermissionDeniedError(
                message=f"Permission denied: {action}:{resource_type}",
                detail={
                    "required_action": action,
                    "required_resource_type": resource_type,
                },
            )
        
        return user
    
    return _check_permission


# Type alias for common dependency
CurrentUser = Annotated[User, Depends(get_current_user)]
