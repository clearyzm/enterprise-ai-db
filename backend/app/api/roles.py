"""Role management API endpoints.

Routes:
- GET /roles - List roles
- POST /roles - Create role
- PATCH /roles/{id} - Update role
- DELETE /roles/{id} - Delete role (system roles protected)
- GET /permissions - List all permissions

All endpoints require manage:role permission.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.models.role import Role, Permission, RolePermission
from app.utils.errors import ConflictError, NotFoundError, ValidationError

router = APIRouter(prefix="/roles", tags=["Roles"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateRoleRequest(BaseModel):
    """Create role request body."""

    name: str = Field(..., min_length=1, max_length=100, description="Role name")
    description: str | None = Field(None, max_length=500, description="Role description")
    permission_ids: list[str] = Field(default_factory=list, description="Permission UUIDs")


class UpdateRoleRequest(BaseModel):
    """Update role request body."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Role name")
    description: str | None = Field(None, max_length=500, description="Role description")
    permission_ids: list[str] | None = Field(None, description="Permission UUIDs (replaces existing)")


class RoleResponse(BaseModel):
    """Role response model."""

    id: str
    name: str
    description: str | None
    is_system: bool
    tenant_id: str
    created_at: str
    updated_at: str
    permissions: list[dict]


class RoleListResponse(BaseModel):
    """Role list response model."""

    roles: list[RoleResponse]
    total: int


class PermissionResponse(BaseModel):
    """Permission response model."""

    id: str
    action: str
    resource_type: str
    description: str | None


class PermissionListResponse(BaseModel):
    """Permission list response model."""

    permissions: list[PermissionResponse]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def _build_role_response(role: Role) -> RoleResponse:
    """Build RoleResponse from Role model."""
    return RoleResponse(
        id=str(role.id),
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        tenant_id=str(role.tenant_id),
        created_at=role.created_at.isoformat(),
        updated_at=role.updated_at.isoformat(),
        permissions=[
            {
                "id": str(p.id),
                "action": p.action,
                "resource_type": p.resource_type,
                "description": p.description,
            }
            for p in role.permissions
        ],
    )


# ============================================================================
# Role Endpoints
# ============================================================================


@router.get("", response_model=RoleListResponse, dependencies=[Depends(require_perm("read", "role"))])
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RoleListResponse:
    """List roles in current tenant."""
    # Build query
    stmt = select(Role).where(Role.tenant_id == user.tenant_id)
    
    # Count total
    count_stmt = select(sa.func.count()).select_from(Role).where(Role.tenant_id == user.tenant_id)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()
    
    # Apply pagination
    stmt = stmt.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(stmt)
    roles = result.scalars().all()
    
    # Build response
    role_responses = [_build_role_response(r) for r in roles]
    
    return RoleListResponse(roles=role_responses, total=total)


@router.post("", response_model=RoleResponse, dependencies=[Depends(require_perm("write", "role"))])
async def create_role(
    request: CreateRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> RoleResponse:
    """Create a new role."""
    # Check if role name already exists in tenant
    stmt = select(Role).where(
        Role.tenant_id == user.tenant_id,
        Role.name == request.name,
    )
    result = await db.execute(stmt)
    existing_role = result.scalar_one_or_none()
    
    if existing_role:
        raise ConflictError(f"Role with name '{request.name}' already exists")
    
    # Create role
    new_role = Role(
        tenant_id=user.tenant_id,
        name=request.name,
        description=request.description,
        is_system=False,  # User-created roles are never system roles
    )
    
    db.add(new_role)
    await db.flush()  # Get role.id
    
    # Assign permissions
    for perm_id_str in request.permission_ids:
        perm_id = UUID(perm_id_str)
        role_perm = RolePermission(role_id=new_role.id, permission_id=perm_id)
        db.add(role_perm)
    
    await db.commit()
    await db.refresh(new_role)
    
    return _build_role_response(new_role)


@router.patch("/{role_id}", response_model=RoleResponse, dependencies=[Depends(require_perm("write", "role"))])
async def update_role(
    role_id: str,
    request: UpdateRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> RoleResponse:
    """Update role information."""
    target_role_id = UUID(role_id)
    
    # Load role
    stmt = select(Role).where(
        Role.id == target_role_id,
        Role.tenant_id == user.tenant_id,
    )
    result = await db.execute(stmt)
    target_role = result.scalar_one_or_none()
    
    if not target_role:
        raise NotFoundError("Role")
    
    # Prevent modification of system roles
    if target_role.is_system:
        raise ValidationError("System roles cannot be modified")
    
    # Update fields
    if request.name is not None:
        # Check name uniqueness
        stmt = select(Role).where(
            Role.tenant_id == user.tenant_id,
            Role.name == request.name,
            Role.id != target_role_id,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ConflictError(f"Role with name '{request.name}' already exists")
        
        target_role.name = request.name
    
    if request.description is not None:
        target_role.description = request.description
    
    # Update permissions if provided
    if request.permission_ids is not None:
        # Remove existing permissions
        await db.execute(
            delete(RolePermission).where(RolePermission.role_id == target_role_id)
        )
        # Add new permissions
        for perm_id_str in request.permission_ids:
            perm_id = UUID(perm_id_str)
            role_perm = RolePermission(role_id=target_role_id, permission_id=perm_id)
            db.add(role_perm)
    
    await db.commit()
    await db.refresh(target_role)
    
    return _build_role_response(target_role)


@router.delete("/{role_id}", status_code=204, dependencies=[Depends(require_perm("delete", "role"))])
async def delete_role(
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> None:
    """Delete role (system roles are protected)."""
    target_role_id = UUID(role_id)
    
    # Load role
    stmt = select(Role).where(
        Role.id == target_role_id,
        Role.tenant_id == user.tenant_id,
    )
    result = await db.execute(stmt)
    target_role = result.scalar_one_or_none()
    
    if not target_role:
        raise NotFoundError("Role")
    
    # Prevent deletion of system roles
    if target_role.is_system:
        raise ValidationError("System roles cannot be deleted")
    
    # Delete role (cascade will remove role_permissions and user_roles)
    await db.delete(target_role)
    await db.commit()


# ============================================================================
# Permission Endpoints
# ============================================================================


@router.get("/permissions", response_model=PermissionListResponse)
async def list_permissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> PermissionListResponse:
    """List all available permissions (global, not tenant-scoped).
    
    This endpoint is available to all authenticated users to see
    what permissions exist in the system.
    """
    # Query all permissions (not tenant-scoped)
    stmt = select(Permission).order_by(Permission.resource_type, Permission.action)
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    
    # Build response
    perm_responses = [
        PermissionResponse(
            id=str(p.id),
            action=p.action,
            resource_type=p.resource_type,
            description=p.description,
        )
        for p in permissions
    ]
    
    return PermissionListResponse(permissions=perm_responses, total=len(perm_responses))
