"""DataSet service — business logic for dataset CRUD and schema validation."""
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import DataSet, DataSetStatus
from app.models.user import User
from app.models.department import Department
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from app.utils.jsonschema import (
    validate_payload,
    validate_schema_definition,
    check_schema_compatibility,
)
from app.services.permission_service import PermissionService

logger = structlog.get_logger(__name__)


class DataSetService:
    """Service for dataset CRUD operations and schema validation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.permission_service = PermissionService(db)

    async def create_dataset(
        self,
        *,
        name: str,
        schema: dict[str, Any],
        tenant_id: UUID,
        created_by: UUID,
        description: str | None = None,
        ui_config: dict[str, Any] | None = None,
        indexes: list[dict[str, Any]] | None = None,
        owner_dept_id: UUID | None = None,
        workflow_id: UUID | None = None,
        sensitivity: str = "internal",
        ai_indexed: bool = True,
    ) -> DataSet:
        """Create a new dataset."""
        # Validate schema definition
        is_valid, error_msg = validate_schema_definition(schema)
        if not is_valid:
            logger.warning("dataset.create.invalid_schema", tenant_id=str(tenant_id), name=name, error=error_msg)
            raise ValidationError(f"Invalid JSON Schema: {error_msg}")
        
        # Check for duplicate name
        stmt = select(func.count()).select_from(DataSet).where(
            DataSet.tenant_id == tenant_id, DataSet.name == name
        )
        result = await self.db.execute(stmt)
        if result.scalar_one() > 0:
            logger.warning("dataset.create.duplicate_name", tenant_id=str(tenant_id), name=name)
            raise ConflictError(f"Dataset '{name}' already exists")
        
        # Validate owner_dept_id if provided
        if owner_dept_id:
            stmt = select(Department).where(Department.id == owner_dept_id, Department.tenant_id == tenant_id)
            result = await self.db.execute(stmt)
            if not result.scalar_one_or_none():
                raise NotFoundError(f"Department {owner_dept_id} not found")
        
        # Create dataset
        dataset = DataSet(
            tenant_id=tenant_id, name=name, description=description, schema=schema,
            ui_config=ui_config or {}, indexes=indexes or [], owner_dept_id=owner_dept_id,
            workflow_id=workflow_id, sensitivity=sensitivity, ai_indexed=ai_indexed,  # type: ignore
            created_by=created_by, status=DataSetStatus.active
        )
        self.db.add(dataset)
        await self.db.commit()
        await self.db.refresh(dataset)
        logger.info("dataset.created", dataset_id=str(dataset.id), tenant_id=str(tenant_id), name=name)
        return dataset

    async def get_dataset(self, dataset_id: UUID, *, for_update: bool = False) -> DataSet:
        """Get dataset by ID."""
        stmt = select(DataSet).where(DataSet.id == dataset_id)
        if for_update:
            stmt = stmt.with_for_update(of=DataSet)
        result = await self.db.execute(stmt)
        dataset = result.scalar_one_or_none()
        if not dataset:
            logger.warning("dataset.not_found", dataset_id=str(dataset_id))
            raise NotFoundError(f"Dataset {dataset_id} not found")
        return dataset

    async def list_datasets(
        self, user: User, *, owner_dept_id: UUID | None = None,
        sensitivity: str | None = None, status: DataSetStatus | None = None,
        limit: int = 100, offset: int = 0
    ) -> tuple[list[DataSet], int]:
        """List datasets accessible to user (with scope filtering)."""
        stmt = select(DataSet).where(DataSet.tenant_id == user.tenant_id)
        count_stmt = select(func.count()).select_from(DataSet).where(DataSet.tenant_id == user.tenant_id)
        
        # Apply scope filtering (Phase 4)
        accessible_dataset_ids = await self.permission_service.get_accessible_dataset_ids(user)
        if accessible_dataset_ids:  # Non-empty list = restricted access
            stmt = stmt.where(DataSet.id.in_(accessible_dataset_ids))
            count_stmt = count_stmt.where(DataSet.id.in_(accessible_dataset_ids))
        # Empty list = full tenant access (no additional filtering)
        
        if owner_dept_id:
            stmt = stmt.where(DataSet.owner_dept_id == owner_dept_id)
            count_stmt = count_stmt.where(DataSet.owner_dept_id == owner_dept_id)
        if sensitivity:
            stmt = stmt.where(DataSet.sensitivity == sensitivity)
            count_stmt = count_stmt.where(DataSet.sensitivity == sensitivity)
        if status:
            stmt = stmt.where(DataSet.status == status)
            count_stmt = count_stmt.where(DataSet.status == status)
        
        stmt = stmt.order_by(DataSet.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        datasets = list(result.scalars().all())
        result = await self.db.execute(count_stmt)
        total = result.scalar_one()
        logger.debug("dataset.list", user_id=str(user.id), count=len(datasets), total=total)
        return datasets, total

    async def update_dataset(
        self, dataset_id: UUID, *, name: str | None = None, description: str | None = None,
        schema: dict[str, Any] | None = None, ui_config: dict[str, Any] | None = None,
        indexes: list[dict[str, Any]] | None = None, owner_dept_id: UUID | None = None,
        workflow_id: UUID | None = None, sensitivity: str | None = None,
        ai_indexed: bool | None = None, status: DataSetStatus | None = None,
        force: bool = False
    ) -> DataSet:
        """Update dataset. Schema changes trigger re-indexing (Phase 7).
        
        Args:
            dataset_id: Dataset UUID
            name: New name (must be unique)
            description: New description
            schema: New JSON Schema (triggers re-indexing and compatibility check)
            ui_config: New UI config
            indexes: New indexes config
            owner_dept_id: New owning department
            workflow_id: New default workflow
            sensitivity: New sensitivity level
            ai_indexed: New ai_indexed flag
            status: New status
            force: If True, allow breaking schema changes (default: False)
        
        Returns:
            Updated DataSet object
        
        Raises:
            NotFoundError: Dataset not found
            ConflictError: Name conflict
            ValidationError: Invalid schema or incompatible schema change
        """
        dataset = await self.get_dataset(dataset_id, for_update=True)
        schema_changed = False
        
        if name is not None and name != dataset.name:
            stmt = select(func.count()).select_from(DataSet).where(
                DataSet.tenant_id == dataset.tenant_id, DataSet.name == name, DataSet.id != dataset_id
            )
            result = await self.db.execute(stmt)
            if result.scalar_one() > 0:
                raise ConflictError(f"Dataset '{name}' already exists")
            dataset.name = name
        
        if description is not None:
            dataset.description = description
        
        if schema is not None:
            is_valid, error_msg = validate_schema_definition(schema)
            if not is_valid:
                raise ValidationError(f"Invalid JSON Schema: {error_msg}")
            
            if schema != dataset.schema:
                # Check backward compatibility
                is_compatible, compat_errors = check_schema_compatibility(dataset.schema, schema)
                if not is_compatible and not force:
                    error_detail = "; ".join(compat_errors)
                    logger.warning(
                        "dataset.update.incompatible_schema",
                        dataset_id=str(dataset_id),
                        errors=compat_errors,
                    )
                    raise ValidationError(
                        f"Schema change is not backward compatible: {error_detail}. "
                        "Use force=true to override and allow breaking changes."
                    )
                
                if not is_compatible and force:
                    logger.warning(
                        "dataset.update.forced_schema_change",
                        dataset_id=str(dataset_id),
                        errors=compat_errors,
                    )
                
                dataset.schema = schema
                schema_changed = True
        
        if ui_config is not None:
            dataset.ui_config = ui_config
        if indexes is not None:
            dataset.indexes = indexes
        if owner_dept_id is not None:
            stmt = select(Department).where(Department.id == owner_dept_id, Department.tenant_id == dataset.tenant_id)
            result = await self.db.execute(stmt)
            if not result.scalar_one_or_none():
                raise NotFoundError(f"Department {owner_dept_id} not found")
            dataset.owner_dept_id = owner_dept_id
        if workflow_id is not None:
            dataset.workflow_id = workflow_id
        if sensitivity is not None:
            dataset.sensitivity = sensitivity  # type: ignore
        if ai_indexed is not None:
            dataset.ai_indexed = ai_indexed
        if status is not None:
            dataset.status = status
        
        await self.db.commit()
        await self.db.refresh(dataset)
        logger.info("dataset.updated", dataset_id=str(dataset_id), schema_changed=schema_changed, forced=force)
        # TODO Phase 7: If schema_changed, enqueue reembed_dataset task
        return dataset

    async def delete_dataset(self, dataset_id: UUID) -> None:
        """Soft delete dataset (set status to archived)."""
        dataset = await self.get_dataset(dataset_id, for_update=True)
        dataset.status = DataSetStatus.archived
        await self.db.commit()
        logger.info("dataset.deleted", dataset_id=str(dataset_id))

    async def validate_payload_against_schema(
        self, dataset_id: UUID, payload: dict[str, Any]
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Validate a payload against dataset schema."""
        dataset = await self.get_dataset(dataset_id)
        try:
            is_valid, errors = validate_payload(payload, dataset.schema, raise_on_error=False)
            logger.debug("dataset.validate_payload", dataset_id=str(dataset_id), is_valid=is_valid, error_count=len(errors))
            return is_valid, errors
        except Exception as e:
            logger.error("dataset.validate_payload.error", dataset_id=str(dataset_id), error=str(e))
            raise ValidationError(f"Validation error: {str(e)}")
