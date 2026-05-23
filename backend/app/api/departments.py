"""Department management API endpoints.

Routes:
- GET /departments - List departments
- POST /departments - Create department
- GET /departments/{id} - Get department details
- PATCH /departments/{id} - Update department
- DELETE /departments/{id} - Delete department

All endpoints require manage:department permission.
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.models.department import Department
from app.utils.errors import ConflictError, NotFoundError, ValidationError

router = APIRouter(prefix="/departments", tags=["Departments"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateDepartmentRequest(BaseModel):
    """Create department request body."""

    name: str = Field(..., min_length=1, max_length=200, description="Department name")
    code: str | None = Field(None, max_length=50, description="Optional short code (e.g., 'FIN', 'SALES')")
    parent_id: str | None = Field(None, description="Parent department UUID (for hierarchical structure)")


class UpdateDepartmentRequest(BaseModel):
    """Update department request body."""

    name: str | None = Field(None, min_length=1, max_length=200, description="Department name")
    code: str | None = Field(None, max_length=50, description="Optional short code")
    parent_id: str | None = Field(None, description="Parent department UUID")


class DepartmentResponse(BaseModel):
    """Department response model."""

    id: str
    name: str
    code: str | None
    parent_id: str | None
    tenant_id: str
    created_at: str
    updated_at: str
    parent: dict | None
    children: list[dict]
    user_count: int


class DepartmentListResponse(BaseModel):
    """Department list response model."""

    departments: list[DepartmentResponse]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def _build_department_response(dept: Department) -> DepartmentResponse:
    """Build DepartmentResponse from Department model.
    
    Note: parent/children/user_count are intentionally returned as None/empty
    to avoid triggering lazy loading on the Department self-referential
    relationships, which causes asyncpg "Was IO attempted in an unexpected
    place" errors. If detailed hierarchy is needed, query separately.
    """
    return DepartmentResponse(
        id=str(dept.id),
        name=dept.name,
        code=dept.code,
        parent_id=str(dept.parent_id) if dept.parent_id else None,
        tenant_id=str(dept.tenant_id),
        created_at=dept.created_at.isoformat(),
        updated_at=dept.updated_at.isoformat(),
        parent=None,
        children=[],
        user_count=0,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=DepartmentListResponse, dependencies=[Depends(require_perm("read", "department"))])
async def list_departments(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    parent_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DepartmentListResponse:
    """List departments in current tenant.
    
    **Query Parameters:**
    - parent_id: Filter by parent department UUID (optional, null = root departments)
    - limit: Max results (1-100, default 50)
    - offset: Pagination offset (default 0)
    """
    # Build query
    stmt = select(Department).where(Department.tenant_id == user.tenant_id)
    
    # Filter by parent_id if specified
    if parent_id is not None:
        if parent_id == "null":
            # Root departments (no parent)
            stmt = stmt.where(Department.parent_id.is_(None))
        else:
            # Children of specific parent
            stmt = stmt.where(Department.parent_id == UUID(parent_id))
    
    # Count total
    count_stmt = select(sa.func.count()).select_from(Department).where(Department.tenant_id == user.tenant_id)
    if parent_id is not None:
        if parent_id == "null":
            count_stmt = count_stmt.where(Department.parent_id.is_(None))
        else:
            count_stmt = count_stmt.where(Department.parent_id == UUID(parent_id))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()
    
    # Apply pagination
    stmt = stmt.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(stmt)
    departments = result.scalars().all()
    
    # Build response
    dept_responses = [_build_department_response(d) for d in departments]
    
    return DepartmentListResponse(departments=dept_responses, total=total)


@router.post("", response_model=DepartmentResponse, dependencies=[Depends(require_perm("write", "department"))])
async def create_department(
    request: CreateDepartmentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DepartmentResponse:
    """Create a new department."""
    # Check if department name already exists in tenant
    stmt = select(Department).where(
        Department.tenant_id == user.tenant_id,
        Department.name == request.name,
    )
    result = await db.execute(stmt)
    existing_dept = result.scalar_one_or_none()
    
    if existing_dept:
        raise ConflictError(f"Department with name '{request.name}' already exists")
    
    # Validate parent_id if provided
    parent_id_uuid = None
    if request.parent_id:
        parent_id_uuid = UUID(request.parent_id)
        stmt = select(Department).where(
            Department.id == parent_id_uuid,
            Department.tenant_id == user.tenant_id,
        )
        result = await db.execute(stmt)
        parent_dept = result.scalar_one_or_none()
        if not parent_dept:
            raise NotFoundError("Parent department")
    
    # Create department
    new_dept = Department(
        tenant_id=user.tenant_id,
        name=request.name,
        code=request.code,
        parent_id=parent_id_uuid,
    )
    
    db.add(new_dept)
    await db.commit()
    await db.refresh(new_dept)
    
    return _build_department_response(new_dept)


@router.get("/{dept_id}", response_model=DepartmentResponse, dependencies=[Depends(require_perm("read", "department"))])
async def get_department(
    dept_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DepartmentResponse:
    """Get department details."""
    target_dept_id = UUID(dept_id)
    
    # Load department
    stmt = select(Department).where(
        Department.id == target_dept_id,
        Department.tenant_id == user.tenant_id,
    )
    result = await db.execute(stmt)
    dept = result.scalar_one_or_none()
    
    if not dept:
        raise NotFoundError("Department")
    
    return _build_department_response(dept)


@router.patch("/{dept_id}", response_model=DepartmentResponse, dependencies=[Depends(require_perm("write", "department"))])
async def update_department(
    dept_id: str,
    request: UpdateDepartmentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DepartmentResponse:
    """Update department information."""
    target_dept_id = UUID(dept_id)
    
    # Load department
    stmt = select(Department).where(
        Department.id == target_dept_id,
        Department.tenant_id == user.tenant_id,
    )
    result = await db.execute(stmt)
    dept = result.scalar_one_or_none()
    
    if not dept:
        raise NotFoundError("Department")
    
    # Update fields
    if request.name is not None:
        # Check name uniqueness
        stmt = select(Department).where(
            Department.tenant_id == user.tenant_id,
            Department.name == request.name,
            Department.id != target_dept_id,
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ConflictError(f"Department with name '{request.name}' already exists")
        
        dept.name = request.name
    
    if request.code is not None:
        dept.code = request.code
    
    if request.parent_id is not None:
        parent_id_uuid = UUID(request.parent_id)
        
        # Prevent circular reference (department cannot be its own ancestor)
        if parent_id_uuid == target_dept_id:
            raise ValidationError("Department cannot be its own parent")
        
        # Validate parent exists
        stmt = select(Department).where(
            Department.id == parent_id_uuid,
            Department.tenant_id == user.tenant_id,
        )
        result = await db.execute(stmt)
        parent_dept = result.scalar_one_or_none()
        if not parent_dept:
            raise NotFoundError("Parent department")
        
        # TODO: Add recursive check to prevent circular references in tree
        # (e.g., A -> B -> C -> A). For Phase 2, simple check is sufficient.
        
        dept.parent_id = parent_id_uuid
    
    await db.commit()
    await db.refresh(dept)
    
    return _build_department_response(dept)


@router.delete("/{dept_id}", status_code=204, dependencies=[Depends(require_perm("delete", "department"))])
async def delete_department(
    dept_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> None:
    """Delete department.
    
    Note: Deleting a department will:
    - Set parent_id to NULL for child departments (ON DELETE SET NULL)
    - Remove user_departments associations (ON DELETE CASCADE)
    - Set owner_dept_id to NULL for datasets (ON DELETE SET NULL)
    """
    target_dept_id = UUID(dept_id)
    
    # Load department
    stmt = select(Department).where(
        Department.id == target_dept_id,
        Department.tenant_id == user.tenant_id,
    )
    result = await db.execute(stmt)
    dept = result.scalar_one_or_none()
    
    if not dept:
        raise NotFoundError("Department")
    
    # Delete department (cascade handled by database)
    await db.delete(dept)
    await db.commit()
