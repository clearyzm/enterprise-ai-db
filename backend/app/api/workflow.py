"""Workflow management API endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowListItem,
    PaginatedWorkflows,
)
from app.models.workflow import Workflow, WorkflowStatus
from app.utils.errors import NotFoundError, ValidationError, ConflictError

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.get("", response_model=PaginatedWorkflows, dependencies=[Depends(require_perm("manage", "workflow"))])
async def list_workflows(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedWorkflows:
    """List workflows in current tenant."""
    from sqlalchemy import select, func, and_

    filters = [Workflow.tenant_id == user.tenant_id]
    if status:
        filters.append(Workflow.status == WorkflowStatus(status))

    # Count total
    count_stmt = select(func.count(Workflow.id)).where(and_(*filters))
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    stmt = (
        select(Workflow)
        .where(and_(*filters))
        .order_by(Workflow.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    result = await db.execute(stmt)
    workflows = result.scalars().all()

    items = [WorkflowListItem.from_orm_workflow(wf) for wf in workflows]
    total_pages = (total + page_size - 1) // page_size

    return PaginatedWorkflows(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=WorkflowResponse, dependencies=[Depends(require_perm("manage", "workflow"))])
async def create_workflow(
    request: WorkflowCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> WorkflowResponse:
    """Create a new workflow."""
    from sqlalchemy import select

    # Check name uniqueness
    stmt = select(Workflow).where(
        Workflow.tenant_id == user.tenant_id,
        Workflow.name == request.name,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise ConflictError(f"Workflow name '{request.name}' already exists")

    # Create workflow
    workflow = Workflow(
        tenant_id=user.tenant_id,
        name=request.name,
        description=request.description,
        steps=[step.model_dump() for step in request.steps],
        status=WorkflowStatus.active,
        created_by=user.id,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return WorkflowResponse.model_validate(workflow)


@router.get("/{workflow_id}", response_model=WorkflowResponse, dependencies=[Depends(require_perm("manage", "workflow"))])
async def get_workflow(
    workflow_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> WorkflowResponse:
    """Get workflow details by ID."""
    from sqlalchemy import select

    stmt = select(Workflow).where(
        Workflow.id == UUID(workflow_id),
        Workflow.tenant_id == user.tenant_id,
    )
    workflow = (await db.execute(stmt)).scalar_one_or_none()
    if not workflow:
        raise NotFoundError("Workflow")

    return WorkflowResponse.model_validate(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowResponse, dependencies=[Depends(require_perm("manage", "workflow"))])
async def update_workflow(
    workflow_id: str,
    request: WorkflowUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> WorkflowResponse:
    """Update workflow steps or status.
    
    Note: Changing steps does not affect pending approvals (they use the workflow version at submission time).
    """
    from sqlalchemy import select

    stmt = select(Workflow).where(
        Workflow.id == UUID(workflow_id),
        Workflow.tenant_id == user.tenant_id,
    )
    workflow = (await db.execute(stmt)).scalar_one_or_none()
    if not workflow:
        raise NotFoundError("Workflow")

    # Check name uniqueness if changing name
    if request.name and request.name != workflow.name:
        check_stmt = select(Workflow).where(
            Workflow.tenant_id == user.tenant_id,
            Workflow.name == request.name,
        )
        existing = (await db.execute(check_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Workflow name '{request.name}' already exists")

    # Update fields
    if request.name is not None:
        workflow.name = request.name
    if request.description is not None:
        workflow.description = request.description
    if request.steps is not None:
        workflow.steps = [step.model_dump() for step in request.steps]
    if request.status is not None:
        workflow.status = WorkflowStatus(request.status)

    await db.commit()
    await db.refresh(workflow)

    return WorkflowResponse.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=204, dependencies=[Depends(require_perm("manage", "workflow"))])
async def delete_workflow(
    workflow_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> None:
    """Delete workflow (only if not referenced by any dataset)."""
    from sqlalchemy import select
    from app.models.dataset import DataSet

    stmt = select(Workflow).where(
        Workflow.id == UUID(workflow_id),
        Workflow.tenant_id == user.tenant_id,
    )
    workflow = (await db.execute(stmt)).scalar_one_or_none()
    if not workflow:
        raise NotFoundError("Workflow")

    # Check if workflow is referenced by any dataset
    check_stmt = select(func.count(DataSet.id)).where(
        DataSet.workflow_id == workflow.id
    )
    ref_count = (await db.execute(check_stmt)).scalar_one()
    if ref_count > 0:
        raise ValidationError(
            f"Cannot delete workflow: referenced by {ref_count} dataset(s)"
        )

    await db.delete(workflow)
    await db.commit()
