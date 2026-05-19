"""Approval API endpoints — inbox, outbox, approve, reject, cancel."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.schemas.workflow import (
    ApprovalActionCreate,
    ApprovalInboxItem,
    ApprovalOutboxItem,
    ApprovalDetail,
    PaginatedApprovals,
    ApprovalActionResponse,
)
from app.services.workflow_engine import WorkflowEngine
from app.utils.errors import NotFoundError

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("/inbox", response_model=PaginatedApprovals, dependencies=[Depends(require_perm("approve", "record"))])
async def get_approval_inbox(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedApprovals:
    """Get pending approvals awaiting my action (inbox)."""
    from sqlalchemy import select, func, and_, or_
    from app.models.record import RecordVersion, RecordVersionState
    from app.models.workflow import Workflow
    from app.models.dataset import DataSet
    from app.models.user import User

    # Find pending versions where I'm a candidate approver
    # This is a simplified implementation - in production, you'd need to resolve
    # approver candidates for each version's current step
    
    stmt = (
        select(RecordVersion)
        .join(DataSet, RecordVersion.dataset_id == DataSet.id)
        .join(Workflow, RecordVersion.workflow_id == Workflow.id)
        .where(
            and_(
                RecordVersion.tenant_id == user.tenant_id,
                RecordVersion.state == RecordVersionState.pending,
                RecordVersion.proposed_by != user.id,  # Exclude own submissions
            )
        )
        .order_by(RecordVersion.created_at.desc())
    )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    stmt = stmt.limit(page_size).offset(offset)
    result = await db.execute(stmt)
    versions = result.scalars().all()

    # Build response items
    items: list[ApprovalInboxItem] = []
    for version in versions:
        # Load related data
        dataset = version.dataset
        workflow = version.workflow if version.workflow_id else None
        proposer = version.proposer

        step_name = ""
        workflow_name = ""
        if workflow and version.current_step < len(workflow.steps):
            step_name = workflow.steps[version.current_step].get("name", f"Step {version.current_step + 1}")
            workflow_name = workflow.name

        items.append(
            ApprovalInboxItem(
                version_id=version.id,
                record_id=version.record_id,
                dataset_id=version.dataset_id,
                dataset_name=dataset.name,
                op=version.op.value,
                current_step=version.current_step,
                step_name=step_name,
                workflow_name=workflow_name,
                proposed_by_id=version.proposed_by,
                proposed_by_email=proposer.email if proposer else None,
                proposed_by_name=proposer.display_name if proposer else None,
                reason=version.reason,
                created_at=version.created_at,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return PaginatedApprovals(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/outbox", response_model=PaginatedApprovals)
async def get_approval_outbox(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedApprovals:
    """Get versions I submitted (outbox)."""
    from sqlalchemy import select, func, and_
    from app.models.record import RecordVersion
    from app.models.workflow import Workflow
    from app.models.dataset import DataSet

    stmt = (
        select(RecordVersion)
        .join(DataSet, RecordVersion.dataset_id == DataSet.id)
        .outerjoin(Workflow, RecordVersion.workflow_id == Workflow.id)
        .where(
            and_(
                RecordVersion.tenant_id == user.tenant_id,
                RecordVersion.proposed_by == user.id,
            )
        )
        .order_by(RecordVersion.created_at.desc())
    )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    stmt = stmt.limit(page_size).offset(offset)
    result = await db.execute(stmt)
    versions = result.scalars().all()

    # Build response items
    items: list[ApprovalOutboxItem] = []
    for version in versions:
        dataset = version.dataset
        workflow = version.workflow if version.workflow_id else None

        step_name = None
        workflow_name = None
        current_step = None

        if version.state.value == "pending" and workflow:
            current_step = version.current_step
            if current_step < len(workflow.steps):
                step_name = workflow.steps[current_step].get("name", f"Step {current_step + 1}")
            workflow_name = workflow.name

        items.append(
            ApprovalOutboxItem(
                version_id=version.id,
                record_id=version.record_id,
                dataset_id=version.dataset_id,
                dataset_name=dataset.name,
                op=version.op.value,
                state=version.state.value,
                current_step=current_step,
                step_name=step_name,
                workflow_name=workflow_name,
                reject_reason=version.reject_reason,
                created_at=version.created_at,
                applied_at=version.applied_at,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return PaginatedApprovals(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{version_id}", response_model=ApprovalDetail)
async def get_approval_detail(
    version_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ApprovalDetail:
    """Get approval detail including diff and actions."""
    from sqlalchemy import select
    from app.models.record import RecordVersion
    from app.models.workflow import Workflow, ApprovalAction
    from app.models.dataset import DataSet

    stmt = (
        select(RecordVersion)
        .where(
            RecordVersion.id == UUID(version_id),
            RecordVersion.tenant_id == user.tenant_id,
        )
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if not version:
        raise NotFoundError("RecordVersion")

    # Load related data
    dataset = version.dataset
    workflow = version.workflow if version.workflow_id else None
    proposer = version.proposer

    # Load approval actions
    actions_stmt = (
        select(ApprovalAction)
        .where(ApprovalAction.version_id == version.id)
        .order_by(ApprovalAction.created_at.asc())
    )
    actions_result = await db.execute(actions_stmt)
    actions = actions_result.scalars().all()

    action_responses = [
        ApprovalActionResponse(
            id=action.id,
            tenant_id=action.tenant_id,
            version_id=action.version_id,
            step_index=action.step_index,
            approver_id=action.approver_id,
            approver_email=action.approver.email if action.approver else None,
            approver_name=action.approver.display_name if action.approver else None,
            action=action.action.value,
            comment=action.comment,
            created_at=action.created_at,
        )
        for action in actions
    ]

    workflow_steps = []
    workflow_name = None
    if workflow:
        workflow_name = workflow.name
        from app.schemas.workflow import WorkflowStep
        workflow_steps = [WorkflowStep(**step) for step in workflow.steps]

    return ApprovalDetail(
        version_id=version.id,
        record_id=version.record_id,
        dataset_id=version.dataset_id,
        dataset_name=dataset.name,
        op=version.op.value,
        state=version.state.value,
        before_payload=version.before_payload,
        after_payload=version.after_payload,
        current_step=version.current_step,
        workflow_id=version.workflow_id,
        workflow_name=workflow_name,
        workflow_steps=workflow_steps,
        proposed_by_id=version.proposed_by,
        proposed_by_email=proposer.email if proposer else None,
        proposed_by_name=proposer.display_name if proposer else None,
        reason=version.reason,
        reject_reason=version.reject_reason,
        created_at=version.created_at,
        applied_at=version.applied_at,
        actions=action_responses,
    )


@router.post("/{version_id}/approve", response_model=ApprovalDetail, dependencies=[Depends(require_perm("approve", "record"))])
async def approve_version(
    version_id: str,
    request: ApprovalActionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ApprovalDetail:
    """Approve a pending version."""
    engine = WorkflowEngine(db)
    version = await engine.approve(UUID(version_id), user, request.comment)
    await db.commit()
    await db.refresh(version)

    # Return updated detail
    return await get_approval_detail(version_id, db, user)


@router.post("/{version_id}/reject", response_model=ApprovalDetail, dependencies=[Depends(require_perm("approve", "record"))])
async def reject_version(
    version_id: str,
    request: ApprovalActionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ApprovalDetail:
    """Reject a pending version."""
    engine = WorkflowEngine(db)
    version = await engine.reject(UUID(version_id), user, request.comment)
    await db.commit()
    await db.refresh(version)

    # Return updated detail
    return await get_approval_detail(version_id, db, user)


@router.post("/{version_id}/cancel", response_model=ApprovalDetail)
async def cancel_version(
    version_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> ApprovalDetail:
    """Cancel a pending version (only by proposer)."""
    engine = WorkflowEngine(db)
    version = await engine.cancel(UUID(version_id), user)
    await db.commit()
    await db.refresh(version)

    # Return updated detail
    return await get_approval_detail(version_id, db, user)
