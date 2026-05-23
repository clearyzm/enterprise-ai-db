"""DataRecord service — business logic for record CRUD with approval workflow.

Phase 5: Real workflow engine integration
- All changes go through record_versions (state='pending')
- WorkflowEngine handles approval flow and apply logic
"""
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import DataSet
from app.models.record import (
    DataRecord,
    RecordVersion,
    RecordStatus,
    RecordVersionOp,
    RecordVersionState,
)
from app.models.user import User
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from app.utils.jsonschema import validate_payload
from app.utils.filter_parser import FilterParser
from app.services.workflow_engine import WorkflowEngine
from app.services.audit_service import log_event
from app.realtime.redis_bus import get_event_bus

logger = structlog.get_logger(__name__)


class RecordService:
    """Service for record CRUD operations with approval workflow."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_record(
        self,
        *,
        dataset_id: UUID,
        payload: dict[str, Any],
        user: User,
        department_id: UUID | None = None,
        reason: str | None = None,
    ) -> tuple[RecordVersion, DataRecord | None]:
        """Submit new record for approval (INSERT operation)."""
        dataset = await self._get_dataset(dataset_id)
        self._validate_payload(payload, dataset)

        version = RecordVersion(
            tenant_id=user.tenant_id,
            record_id=None,
            dataset_id=dataset_id,
            op=RecordVersionOp.insert,
            before_payload=None,
            after_payload=payload,
            state=RecordVersionState.pending,
            workflow_id=dataset.workflow_id,
            current_step=0,
            proposed_by=user.id,
            reason=reason,
        )
        self.db.add(version)
        await self.db.flush()

        logger.info(
            "record.create.submitted",
            version_id=str(version.id),
            dataset_id=str(dataset_id),
            user_id=str(user.id),
        )

        # Use workflow engine to handle approval flow
        engine = WorkflowEngine(self.db)
        version = await engine.submit(version, user)
        await self.db.commit()
        await self.db.refresh(version)

        # Load record if applied
        record = None
        if version.record_id:
            record = await self._get_record(version.record_id)

        # Publish real-time event if record was immediately applied
        if version.state == RecordVersionState.applied and record is not None:
            await get_event_bus().publish(
                tenant_id=user.tenant_id,
                channel=f"dataset:{dataset_id}",
                event={
                    "type": "record.upserted",
                    "record_id": str(record.id),
                    "version": record.version,
                    "by": str(user.id),
                },
            )

        return version, record

    async def update_record(
        self,
        *,
        record_id: UUID,
        payload: dict[str, Any],
        expected_version: int,
        user: User,
        reason: str | None = None,
    ) -> tuple[RecordVersion, DataRecord | None]:
        """Submit record update for approval (UPDATE operation)."""
        record = await self._get_record(record_id, for_update=True)
        if record.version != expected_version:
            logger.warning(
                "record.update.version_conflict",
                record_id=str(record_id),
                expected=expected_version,
                actual=record.version,
            )
            raise ConflictError(
                message=f"Version conflict: expected {expected_version}, "
                f"but current version is {record.version}",
                code="VERSION_CONFLICT",
            )

        dataset = await self._get_dataset(record.dataset_id)
        self._validate_payload(payload, dataset)

        # Store current version in before_payload for optimistic locking
        before_payload = dict(record.payload)
        before_payload["__version"] = record.version

        version = RecordVersion(
            tenant_id=user.tenant_id,
            record_id=record_id,
            dataset_id=record.dataset_id,
            op=RecordVersionOp.update,
            before_payload=before_payload,
            after_payload=payload,
            state=RecordVersionState.pending,
            workflow_id=dataset.workflow_id,
            current_step=0,
            proposed_by=user.id,
            reason=reason,
        )
        self.db.add(version)
        await self.db.flush()

        logger.info(
            "record.update.submitted",
            version_id=str(version.id),
            record_id=str(record_id),
            user_id=str(user.id),
        )

        # Use workflow engine to handle approval flow
        engine = WorkflowEngine(self.db)
        version = await engine.submit(version, user)
        await self.db.commit()
        await self.db.refresh(version)

        # Audit log: record update submitted
        await log_event(
            self.db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="update_record",
            resource_type="record",
            resource_id=str(record_id),
            detail={
                "version_id": str(version.id),
                "dataset_id": str(dataset.id),
                "dataset_name": dataset.name,
                "op": "update",
                "state": version.state.value,
                "expected_version": expected_version,
                "auto_applied": version.state.value == "applied",
                "reason": reason,
            },
        )
        await self.db.commit()

        # Load record if applied
        updated_record = None
        if version.state == RecordVersionState.applied:
            updated_record = await self._get_record(record_id)

        # Publish real-time event if record was immediately applied
        if updated_record is not None:
            await get_event_bus().publish(
                tenant_id=user.tenant_id,
                channel=f"dataset:{updated_record.dataset_id}",
                event={
                    "type": "record.upserted",
                    "record_id": str(record_id),
                    "version": updated_record.version,
                    "by": str(user.id),
                },
            )

        return version, updated_record

    async def delete_record(
        self,
        *,
        record_id: UUID,
        user: User,
        reason: str | None = None,
    ) -> RecordVersion:
        """Submit record deletion for approval (DELETE operation)."""
        record = await self._get_record(record_id, for_update=True)

        # Store current version in before_payload for optimistic locking
        before_payload = dict(record.payload)
        before_payload["__version"] = record.version

        version = RecordVersion(
            tenant_id=user.tenant_id,
            record_id=record_id,
            dataset_id=record.dataset_id,
            op=RecordVersionOp.delete,
            before_payload=before_payload,
            after_payload=None,
            state=RecordVersionState.pending,
            workflow_id=None,
            current_step=0,
            proposed_by=user.id,
            reason=reason,
        )
        self.db.add(version)
        await self.db.flush()

        logger.info(
            "record.delete.submitted",
            version_id=str(version.id),
            record_id=str(record_id),
            user_id=str(user.id),
        )

        # Use workflow engine to handle approval flow
        engine = WorkflowEngine(self.db)
        version = await engine.submit(version, user)
        await self.db.commit()
        await self.db.refresh(version)

        # Publish real-time event if record was immediately soft-deleted
        if version.state == RecordVersionState.applied and record_id is not None:
            await get_event_bus().publish(
                tenant_id=user.tenant_id,
                channel=f"dataset:{version.dataset_id}",
                event={
                    "type": "record.deleted",
                    "record_id": str(record_id),
                    "by": str(user.id),
                },
            )

        return version

    async def list_records(
        self,
        *,
        dataset_id: UUID,
        user: User,
        filters: dict[str, str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[DataRecord], int]:
        """List records with filtering, sorting, and pagination."""
        dataset = await self._get_dataset(dataset_id)

        stmt = select(DataRecord).where(
            and_(
                DataRecord.tenant_id == user.tenant_id,
                DataRecord.dataset_id == dataset_id,
                DataRecord.status == RecordStatus.active,
            )
        )
        count_stmt = select(func.count()).select_from(DataRecord).where(
            and_(
                DataRecord.tenant_id == user.tenant_id,
                DataRecord.dataset_id == dataset_id,
                DataRecord.status == RecordStatus.active,
            )
        )

        if filters:
            parser = FilterParser(dataset.schema)
            filter_clauses = parser.parse_filters(filters)
            stmt = stmt.where(and_(*filter_clauses))
            count_stmt = count_stmt.where(and_(*filter_clauses))

        stmt = stmt.order_by(DataRecord.updated_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        records = list(result.scalars().all())

        result = await self.db.execute(count_stmt)
        total = result.scalar_one()

        logger.debug(
            "record.list",
            dataset_id=str(dataset_id),
            user_id=str(user.id),
            count=len(records),
            total=total,
        )

        return records, total

    async def get_record(self, record_id: UUID) -> DataRecord:
        """Get record by ID."""
        return await self._get_record(record_id)

    async def get_record_history(self, record_id: UUID) -> list[RecordVersion]:
        """Get all versions for a record."""
        await self._get_record(record_id)

        stmt = (
            select(RecordVersion)
            .where(RecordVersion.record_id == record_id)
            .order_by(RecordVersion.created_at.desc())
        )
        result = await self.db.execute(stmt)
        versions = list(result.scalars().all())

        logger.debug(
            "record.history",
            record_id=str(record_id),
            version_count=len(versions),
        )

        return versions

    async def _get_dataset(self, dataset_id: UUID) -> DataSet:
        """Get dataset by ID."""
        stmt = select(DataSet).where(DataSet.id == dataset_id)
        result = await self.db.execute(stmt)
        dataset = result.scalar_one_or_none()
        if not dataset:
            logger.warning("record.dataset_not_found", dataset_id=str(dataset_id))
            raise NotFoundError(f"Dataset {dataset_id} not found")
        return dataset

    async def _get_record(
        self, record_id: UUID, *, for_update: bool = False
    ) -> DataRecord:
        """Get record by ID."""
        stmt = select(DataRecord).where(
            and_(
                DataRecord.id == record_id,
                DataRecord.status == RecordStatus.active,
            )
        )
        if for_update:
            stmt = stmt.with_for_update(of=DataRecord)

        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            logger.warning("record.not_found", record_id=str(record_id))
            raise NotFoundError(f"Record {record_id} not found")
        return record

    def _validate_payload(self, payload: dict[str, Any], dataset: DataSet) -> None:
        """Validate payload against dataset schema."""
        is_valid, errors = validate_payload(
            payload, dataset.schema, raise_on_error=False
        )
        if not is_valid:
            error_detail = "; ".join([e["message"] for e in errors])
            logger.warning(
                "record.validation_failed",
                dataset_id=str(dataset.id),
                errors=errors,
            )
            raise ValidationError(f"Payload validation failed: {error_detail}")
