"""User management API endpoints.

Routes:
- GET /users - List users (with department filtering)
- POST /users - Create/invite user
- GET /users/{id} - Get user details
- PATCH /users/{id} - Update user
- DELETE /users/{id} - Soft delete user
- POST /users/{id}/roles - Assign role to user
- DELETE /users/{id}/roles/{user_role_id} - Revoke role from user

All endpoints require manage:user permission (except GET /users/{id} for self).
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func, delete
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user, require_perm
from app.models.user import User, UserStatus
from app.models.role import UserRole
from app.models.department import UserDepartment
from app.utils.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.utils.hashing import hash_password
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/users", tags=["Users"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateUserRequest(BaseModel):
    """Create user request body."""

    email: EmailStr = Field(..., description="User email address")
    display_name: str = Field(..., min_length=1, max_length=200, description="User display name")
    password: str = Field(..., min_length=10, description="Initial password (min 10 characters)")
    department_ids: list[str] = Field(default_factory=list, description="Department UUIDs")
    role_ids: list[str] = Field(default_factory=list, description="Role UUIDs to assign")
    is_tenant_admin: bool = Field(default=False, description="Whether user is tenant admin")


class UpdateUserRequest(BaseModel):
    """Update user request body."""

    display_name: str | None = Field(None, min_length=1, max_length=200, description="User display name")
    status: UserStatus | None = Field(None, description="User status")
    department_ids: list[str] | None = Field(None, description="Department UUIDs (replaces existing)")


class AssignRoleRequest(BaseModel):
    """Assign role to user request body."""

    role_id: str = Field(..., description="Role UUID")
    scope: dict = Field(default_factory=dict, description="Permission scope (empty = full tenant)")


class UserResponse(BaseModel):
    """User response model."""

    id: str
    email: str
    display_name: str
    status: str
    is_tenant_admin: bool
    tenant_id: str
    last_login_at: str | None
    created_at: str
    updated_at: str
    departments: list[dict]
    roles: list[dict]


class UserListResponse(BaseModel):
    """User list response model."""

    users: list[UserResponse]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def _build_user_response(user: User) -> UserResponse:
    """Build UserResponse from User model."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        status=user.status.value,
        is_tenant_admin=user.is_tenant_admin,
        tenant_id=str(user.tenant_id),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        departments=[
            {"id": str(ud.department_id), "name": ud.department.name, "is_primary": ud.is_primary}
            for ud in user.user_departments
        ],
        roles=[
            {"id": str(ur.role_id), "name": ur.role.name, "scope": ur.scope}
            for ur in user.user_roles
        ],
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=UserListResponse, dependencies=[Depends(require_perm("read", "user"))])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    department_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    """List users in current tenant with optional department filtering."""
    # Build base query
    stmt = select(User).where(User.tenant_id == user.tenant_id)
    
    # Filter by department if specified
    if department_id:
        dept_uuid = UUID(department_id)
        # Join with user_departments and filter
        stmt = stmt.join(User.user_departments).where(
            UserDepartment.department_id == dept_uuid
        )
    
    # Count total (before pagination)
    count_stmt = select(func.count()).select_from(User).where(User.tenant_id == user.tenant_id)
    if department_id:
        count_stmt = count_stmt.join(User.user_departments).where(
            UserDepartment.department_id == UUID(department_id)
        )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()
    
    # Apply pagination
    stmt = stmt.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    # Build response
    user_responses = [_build_user_response(u) for u in users]
    
    return UserListResponse(users=user_responses, total=total)


@router.post("", response_model=UserResponse, dependencies=[Depends(require_perm("write", "user"))])
async def create_user(
    request: CreateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> UserResponse:
    """Create/invite a new user."""
    # Check if email already exists in tenant
    stmt = select(User).where(
        User.tenant_id == user.tenant_id,
        User.email == request.email,
    )
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise ConflictError(f"User with email {request.email} already exists")
    
    # Create user
    new_user = User(
        tenant_id=user.tenant_id,
        email=request.email,
        display_name=request.display_name,
        password_hash=hash_password(request.password),
        status=UserStatus.active,
        is_tenant_admin=request.is_tenant_admin,
    )
    
    db.add(new_user)
    await db.flush()  # Get user.id
    
    # Assign departments
    for dept_id_str in request.department_ids:
        dept_id = UUID(dept_id_str)
        user_dept = UserDepartment(user_id=new_user.id, department_id=dept_id)
        db.add(user_dept)
    
    # Assign roles (with empty scope = full tenant)
    for role_id_str in request.role_ids:
        role_id = UUID(role_id_str)
        user_role = UserRole(user_id=new_user.id, role_id=role_id, scope={})
        db.add(user_role)
    
    await db.commit()
    await db.refresh(new_user)
    
    return _build_user_response(new_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> UserResponse:
    """Get user details. Requires manage:user permission OR user is requesting their own info."""
    target_user_id = UUID(user_id)
    
    # Check permission: manage:user OR self
    perm_service = PermissionService(db)
    is_self = target_user_id == current_user.id
    has_manage_perm = await perm_service.check(current_user, "read", "user")
    
    if not is_self and not has_manage_perm:
        raise PermissionDeniedError("You can only view your own profile")
    
    # Load user
    stmt = select(User).where(
        User.id == target_user_id,
        User.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()
    
    if not target_user:
        raise NotFoundError("User")
    
    return _build_user_response(target_user)


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_perm("write", "user"))])
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> UserResponse:
    """Update user information."""
    target_user_id = UUID(user_id)
    
    # Load user
    stmt = select(User).where(
        User.id == target_user_id,
        User.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()
    
    if not target_user:
        raise NotFoundError("User")
    
    # Update fields
    if request.display_name is not None:
        target_user.display_name = request.display_name
    
    if request.status is not None:
        target_user.status = request.status
    
    # Update departments if provided
    if request.department_ids is not None:
        # Remove existing
        await db.execute(
            delete(UserDepartment).where(UserDepartment.user_id == target_user_id)
        )
        # Add new
        for dept_id_str in request.department_ids:
            dept_id = UUID(dept_id_str)
            user_dept = UserDepartment(user_id=target_user_id, department_id=dept_id)
            db.add(user_dept)
    
    await db.commit()
    await db.refresh(target_user)
    
    return _build_user_response(target_user)


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_perm("delete", "user"))])
async def delete_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> None:
    """Soft delete user (set status to disabled)."""
    target_user_id = UUID(user_id)
    
    # Load user
    stmt = select(User).where(
        User.id == target_user_id,
        User.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()
    
    if not target_user:
        raise NotFoundError("User")
    
    # Soft delete
    target_user.status = UserStatus.disabled
    await db.commit()


@router.post("/{user_id}/roles", status_code=201, dependencies=[Depends(require_perm("write", "role"))])
async def assign_role(
    user_id: str,
    request: AssignRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> dict:
    """Assign role to user with optional scope."""
    target_user_id = UUID(user_id)
    role_id = UUID(request.role_id)
    
    # Verify user exists in tenant
    stmt = select(User).where(
        User.id == target_user_id,
        User.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise NotFoundError("User")
    
    # Create user role assignment
    user_role = UserRole(
        user_id=target_user_id,
        role_id=role_id,
        scope=request.scope,
    )
    db.add(user_role)
    await db.commit()
    await db.refresh(user_role)
    
    return {
        "user_role_id": str(user_role.id),
        "message": "Role assigned successfully",
    }


@router.delete("/{user_id}/roles/{user_role_id}", status_code=204, dependencies=[Depends(require_perm("write", "role"))])
async def revoke_role(
    user_id: str,
    user_role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> None:
    """Revoke role from user."""
    target_user_id = UUID(user_id)
    ur_id = UUID(user_role_id)
    
    # Delete user role
    stmt = delete(UserRole).where(
        UserRole.id == ur_id,
        UserRole.user_id == target_user_id,
    )
    result = await db.execute(stmt)
    
    if result.rowcount == 0:
        raise NotFoundError("User role assignment")
    
    await db.commit()
