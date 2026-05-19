"""DataRecord management API endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.schemas.record import (
    CreateRecordRequest,
    UpdateRecordRequest,
    DeleteRecordRequest,
    DataRecordResponse,
    RecordListResponse,
    RecordHistoryResponse,
    SubmitRecordResponse,
    RecordVersionResponse,
)
from app.services.record_service import RecordService
from app.models.record import DataRecord, RecordVersion

router = APIRouter(prefix="/datasets/{dataset_id}/records", tags=["Records"])


def _build_record_response(record: DataRecord) -> DataRecordResponse:
    """Build DataRecordResponse from DataRecord model."""
    return DataRecordResponse(
        id=record.id,
        dataset_id=record.dataset_id,
        department_id=record.department_id,
        payload=record.payload,
        status=record.status,
        version=record.version,
        created_by=record.created_by,
        updated_by=record.updated_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _build_version_response(version: RecordVersion) -> RecordVersionResponse:
    """Build RecordVersionResponse from RecordVersion model."""
    return RecordVersionResponse(
        id=version.id,
        record_id=version.record_id,
        dataset_id=version.dataset_id,
        op=version.op,
        before_payload=version.before_payload,
        after_payload=version.after_payload,
        state=version.state,
        workflow_id=version.workflow_id,
        current_step=version.current_step,
        proposed_by=version.proposed_by,
        applied_at=version.applied_at,
        reason=version.reason,
        reject_reason=version.reject_reason,
        created_at=version.created_at,
    )


@router.get(
    "",
    response_model=RecordListResponse,
    dependencies=[Depends(require_perm("read", "record"))],
)
async def list_records(
    dataset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordListResponse:
    """List records with filtering, sorting, and pagination.
    
    **Query Parameters:**
    - limit: Page size (1-100, default 20)
    - offset: Offset for pagination (default 0)
    - Filter syntax: field__op=value
      - Operators: eq, ne, gt, gte, lt, lte, in, contains
      - Examples: ?amount__gte=100&status__eq=paid
    
    **Returns:**
    - Paginated list of records
    """
    service = RecordService(db)
    
    # TODO: Parse filter parameters from request.query_params
    # For now, pass empty filters
    filters: dict[str, str] = {}
    
    records, total = await service.list_records(
        dataset_id=UUID(dataset_id),
        user=user,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    page = (offset // limit) + 1
    
    return RecordListResponse(
        items=[_build_record_response(r) for r in records],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=SubmitRecordResponse,
    dependencies=[Depends(require_perm("write", "record"))],
)
async def create_record(
    dataset_id: str,
    request: CreateRecordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> SubmitRecordResponse:
    """Submit new record for approval (INSERT operation).
    
    Phase 4: Auto-approval workflow
    - Creates record_version with state='pending'
    - Immediately applies (returns state='applied' and record)
    
    Phase 5: Real workflow
    - Returns state='pending', record=None until approved
    
    **Request Body:**
    - payload: Record data (validated against dataset.schema)
    - department_id: Owning department UUID (optional)
    - reason: Reason for creating record (optional)
    
    **Returns:**
    - version_id: RecordVersion UUID
    - state: Workflow state ('applied' in Phase 4)
    - record: Applied record (Phase 4) or None (Phase 5 pending)
    """
    service = RecordService(db)
    
    version, record = await service.create_record(
        dataset_id=UUID(dataset_id),
        payload=request.payload,
        user=user,
        department_id=request.department_id,
        reason=request.reason,
    )
    
    return SubmitRecordResponse(
        version_id=version.id,
        state=version.state,
        record=_build_record_response(record) if record else None,
    )


@router.get(
    "/{record_id}",
    response_model=DataRecordResponse,
    dependencies=[Depends(require_perm("read", "record"))],
)
async def get_record(
    dataset_id: str,
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DataRecordResponse:
    """Get record details by ID (includes version for optimistic locking).
    
    **Returns:**
    - Record details with current version number
    """
    service = RecordService(db)
    record = await service.get_record(UUID(record_id))
    return _build_record_response(record)


@router.patch(
    "/{record_id}",
    response_model=SubmitRecordResponse,
    dependencies=[Depends(require_perm("write", "record"))],
)
async def update_record(
    dataset_id: str,
    record_id: str,
    request: UpdateRecordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> SubmitRecordResponse:
    """Submit record update for approval (UPDATE operation).
    
    Requires expected_version for optimistic locking.
    
    **Request Body:**
    - payload: Updated record data (validated against dataset.schema)
    - expected_version: Expected current version (optimistic lock)
    - reason: Reason for updating record (optional)
    
    **Returns:**
    - version_id: RecordVersion UUID
    - state: Workflow state ('applied' in Phase 4)
    - record: Updated record (Phase 4) or None (Phase 5 pending)
    
    **Errors:**
    - 409: Version conflict (record was modified by another user)
    """
    service = RecordService(db)
    
    version, record = await service.update_record(
        record_id=UUID(record_id),
        payload=request.payload,
        expected_version=request.expected_version,
        user=user,
        reason=request.reason,
    )
    
    return SubmitRecordResponse(
        version_id=version.id,
        state=version.state,
        record=_build_record_response(record) if record else None,
    )


@router.delete(
    "/{record_id}",
    response_model=RecordVersionResponse,
    dependencies=[Depends(require_perm("delete", "record"))],
)
async def delete_record(
    dataset_id: str,
    record_id: str,
    request: DeleteRecordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> RecordVersionResponse:
    """Submit record deletion for approval (DELETE operation).
    
    Phase 4: Auto-approval workflow (immediate soft delete)
    Phase 5: Real workflow (pending until approved)
    
    **Request Body:**
    - reason: Reason for deleting record (optional)
    
    **Returns:**
    - RecordVersion with state='applied' (Phase 4)
    """
    service = RecordService(db)
    
    version = await service.delete_record(
        record_id=UUID(record_id),
        user=user,
        reason=request.reason,
    )
    
    return _build_version_response(version)


@router.get(
    "/{record_id}/history",
    response_model=RecordHistoryResponse,
    dependencies=[Depends(require_perm("read", "record"))],
)
async def get_record_history(
    dataset_id: str,
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> RecordHistoryResponse:
    """Get all versions for a record (history + pending changes).
    
    **Returns:**
    - record_id: Record UUID
    - versions: List of RecordVersion (newest first)
    """
    service = RecordService(db)
    
    versions = await service.get_record_history(UUID(record_id))
    
    return RecordHistoryResponse(
        record_id=UUID(record_id),
        versions=[_build_version_response(v) for v in versions],
    )


# Alternative route for getting single record by ID (without dataset_id prefix)
record_router = APIRouter(prefix="/records", tags=["Records"])


@record_router.get(
    "/{record_id}",
    response_model=DataRecordResponse,
    dependencies=[Depends(require_perm("read", "record"))],
)
async def get_record_by_id(
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DataRecordResponse:
    """Get record details by ID (alternative route without dataset_id).
    
    **Returns:**
    - Record details with current version number
    """
    service = RecordService(db)
    record = await service.get_record(UUID(record_id))
    return _build_record_response(record)
