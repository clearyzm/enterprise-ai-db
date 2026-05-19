"""DataSet management API endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.schemas.dataset import (
    CreateDataSetRequest, UpdateDataSetRequest, ValidatePayloadRequest,
    DataSetResponse, DataSetListResponse, ValidatePayloadResponse,
    ImportTaskResponse, ExportTaskResponse,
)
from app.services.dataset_service import DataSetService
from app.utils.errors import NotImplementedError

router = APIRouter(prefix="/datasets", tags=["DataSets"])


def _build_dataset_response(dataset: "DataSet") -> DataSetResponse:  # type: ignore
    """Build DataSetResponse from DataSet model."""
    from app.models.dataset import DataSet
    return DataSetResponse(
        id=str(dataset.id), tenant_id=str(dataset.tenant_id), name=dataset.name,
        description=dataset.description, schema=dataset.schema, ui_config=dataset.ui_config,
        indexes=dataset.indexes, owner_dept_id=str(dataset.owner_dept_id) if dataset.owner_dept_id else None,
        workflow_id=str(dataset.workflow_id) if dataset.workflow_id else None, ai_indexed=dataset.ai_indexed,
        sensitivity=dataset.sensitivity.value, status=dataset.status.value,
        created_by=str(dataset.created_by) if dataset.created_by else None,
        created_at=dataset.created_at.isoformat(), updated_at=dataset.updated_at.isoformat(),
        owner_department={"id": str(dataset.owner_department.id), "name": dataset.owner_department.name} if dataset.owner_department else None,
        creator={"id": str(dataset.creator.id), "email": dataset.creator.email, "display_name": dataset.creator.display_name} if dataset.creator else None,
    )


@router.get("", response_model=DataSetListResponse, dependencies=[Depends(require_perm("read", "dataset"))])
async def list_datasets(
    db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
    owner_dept_id: Annotated[str | None, Query()] = None, sensitivity: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DataSetListResponse:
    """List datasets accessible to current user."""
    service = DataSetService(db)
    owner_dept_uuid = UUID(owner_dept_id) if owner_dept_id else None
    from app.models.dataset import DataSetStatus
    status_enum = DataSetStatus(status) if status else None
    datasets, total = await service.list_datasets(user, owner_dept_id=owner_dept_uuid, sensitivity=sensitivity, status=status_enum, limit=limit, offset=offset)
    return DataSetListResponse(datasets=[_build_dataset_response(ds) for ds in datasets], total=total)


@router.post("", response_model=DataSetResponse, dependencies=[Depends(require_perm("manage", "dataset"))])
async def create_dataset(
    request: CreateDataSetRequest, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
) -> DataSetResponse:
    """Create a new dataset."""
    service = DataSetService(db)
    owner_dept_uuid = UUID(request.owner_dept_id) if request.owner_dept_id else None
    workflow_uuid = UUID(request.workflow_id) if request.workflow_id else None
    dataset = await service.create_dataset(
        name=request.name, schema=request.schema, tenant_id=user.tenant_id, created_by=user.id,
        description=request.description, ui_config=request.ui_config, indexes=request.indexes,
        owner_dept_id=owner_dept_uuid, workflow_id=workflow_uuid, sensitivity=request.sensitivity.value, ai_indexed=request.ai_indexed,
    )
    return _build_dataset_response(dataset)


@router.get("/{dataset_id}", response_model=DataSetResponse, dependencies=[Depends(require_perm("read", "dataset"))])
async def get_dataset(dataset_id: str, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser) -> DataSetResponse:
    """Get dataset details by ID."""
    service = DataSetService(db)
    dataset = await service.get_dataset(UUID(dataset_id))
    return _build_dataset_response(dataset)


@router.patch("/{dataset_id}", response_model=DataSetResponse, dependencies=[Depends(require_perm("manage", "dataset"))])
async def update_dataset(
    dataset_id: str, request: UpdateDataSetRequest, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
) -> DataSetResponse:
    """Update dataset. Schema changes trigger re-indexing (Phase 7).
    
    **Path Parameters:**
    - dataset_id: Dataset UUID
    
    **Request Body:**
    - All fields are optional
    - Schema changes are checked for backward compatibility
    - Use force=true to allow breaking schema changes
    
    **Returns:**
    - Updated dataset details
    
    **Errors:**
    - 422: Schema change is not backward compatible (without force=true)
    """
    service = DataSetService(db)
    owner_dept_uuid = UUID(request.owner_dept_id) if request.owner_dept_id else None
    workflow_uuid = UUID(request.workflow_id) if request.workflow_id else None
    dataset = await service.update_dataset(
        UUID(dataset_id), name=request.name, description=request.description, schema=request.schema,
        ui_config=request.ui_config, indexes=request.indexes, owner_dept_id=owner_dept_uuid,
        workflow_id=workflow_uuid, sensitivity=request.sensitivity.value if request.sensitivity else None,
        ai_indexed=request.ai_indexed, status=request.status, force=request.force,
    )
    return _build_dataset_response(dataset)


@router.delete("/{dataset_id}", status_code=204, dependencies=[Depends(require_perm("manage", "dataset"))])
async def delete_dataset(dataset_id: str, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser) -> None:
    """Soft delete dataset (set status to archived)."""
    service = DataSetService(db)
    await service.delete_dataset(UUID(dataset_id))


@router.post("/{dataset_id}/validate", response_model=ValidatePayloadResponse, dependencies=[Depends(require_perm("write", "dataset"))])
async def validate_payload(
    dataset_id: str, request: ValidatePayloadRequest, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
) -> ValidatePayloadResponse:
    """Validate a payload against dataset schema without persisting."""
    service = DataSetService(db)
    is_valid, errors = await service.validate_payload_against_schema(UUID(dataset_id), request.payload)
    return ValidatePayloadResponse(valid=is_valid, errors=errors)


@router.post("/{dataset_id}/import", response_model=ImportTaskResponse, dependencies=[Depends(require_perm("manage", "dataset"))])
async def import_dataset(
    dataset_id: str, file: Annotated[UploadFile, File(description="CSV/XLSX/JSON file")],
    db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
) -> ImportTaskResponse:
    """Batch import records from CSV/XLSX/JSON file (Phase 4+)."""
    raise NotImplementedError("Batch import will be implemented in Phase 4")


@router.get("/{dataset_id}/export", response_model=ExportTaskResponse, dependencies=[Depends(require_perm("read", "dataset"))])
async def export_dataset(
    dataset_id: str, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser,
    format: Annotated[str, Query()] = "csv",
) -> ExportTaskResponse:
    """Export dataset records to CSV/XLSX/JSON (Phase 4+)."""
    raise NotImplementedError("Export will be implemented in Phase 4")
