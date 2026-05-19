"""Pydantic schemas for DataRecord API validation and serialization.

Request/Response models for record CRUD operations with approval workflow.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.record import RecordStatus, RecordVersionOp, RecordVersionState


# ============================================================================
# Request Models
# ============================================================================


class CreateRecordRequest(BaseModel):
    """Create record request body (submits to approval workflow).
    
    Example:
        {
            "payload": {
                "order_no": "AB12345678",
                "amount": 100.50,
                "customer": "Acme Corp"
            },
            "department_id": "uuid-here",
            "reason": "New customer order"
        }
    """

    payload: dict[str, Any] = Field(
        ...,
        description="Record data (validated against dataset.schema)",
    )

    department_id: UUID | None = Field(
        None,
        description="Owning department UUID (nullable)",
    )

    reason: str | None = Field(
        None,
        max_length=2000,
        description="Reason for creating this record",
    )

    @field_validator("payload")
    @classmethod
    def validate_payload_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Ensure payload is not empty."""
        if not v:
            raise ValueError("payload cannot be empty")
        return v


class UpdateRecordRequest(BaseModel):
    """Update record request body (submits to approval workflow).
    
    Requires expected_version for optimistic locking.
    
    Example:
        {
            "payload": {
                "order_no": "AB12345678",
                "amount": 150.75,
                "customer": "Acme Corp"
            },
            "expected_version": 3,
            "reason": "Price adjustment"
        }
    """

    payload: dict[str, Any] = Field(
        ...,
        description="Updated record data (validated against dataset.schema)",
    )

    expected_version: int = Field(
        ...,
        ge=1,
        description="Expected current version (optimistic lock)",
    )

    reason: str | None = Field(
        None,
        max_length=2000,
        description="Reason for updating this record",
    )

    @field_validator("payload")
    @classmethod
    def validate_payload_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Ensure payload is not empty."""
        if not v:
            raise ValueError("payload cannot be empty")
        return v


class DeleteRecordRequest(BaseModel):
    """Delete record request body (submits to approval workflow).
    
    Example:
        {
            "reason": "Duplicate entry"
        }
    """

    reason: str | None = Field(
        None,
        max_length=2000,
        description="Reason for deleting this record",
    )


# ============================================================================
# Response Models
# ============================================================================


class RecordVersionResponse(BaseModel):
    """RecordVersion response (returned after submit operations).
    
    Example:
        {
            "id": "uuid-here",
            "record_id": "uuid-here",
            "dataset_id": "uuid-here",
            "op": "update",
            "state": "pending",
            "proposed_by": "uuid-here",
            "reason": "Price adjustment",
            "created_at": "2024-01-15T10:30:00Z"
        }
    """

    id: UUID = Field(..., description="Version UUID")
    record_id: UUID | None = Field(None, description="Target record UUID (NULL for insert)")
    dataset_id: UUID = Field(..., description="Parent dataset UUID")
    op: RecordVersionOp = Field(..., description="Operation type")
    before_payload: dict[str, Any] | None = Field(None, description="Payload before change")
    after_payload: dict[str, Any] | None = Field(None, description="Payload after change")
    state: RecordVersionState = Field(..., description="Workflow state")
    workflow_id: UUID | None = Field(None, description="Workflow UUID")
    current_step: int = Field(..., description="Current workflow step")
    proposed_by: UUID = Field(..., description="Proposer user UUID")
    applied_at: datetime | None = Field(None, description="Applied timestamp")
    reason: str | None = Field(None, description="Change reason")
    reject_reason: str | None = Field(None, description="Rejection reason")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = {"from_attributes": True}


class DataRecordResponse(BaseModel):
    """DataRecord response (current active version).
    
    Example:
        {
            "id": "uuid-here",
            "dataset_id": "uuid-here",
            "department_id": "uuid-here",
            "payload": {
                "order_no": "AB12345678",
                "amount": 150.75,
                "customer": "Acme Corp"
            },
            "status": "active",
            "version": 3,
            "created_by": "uuid-here",
            "updated_by": "uuid-here",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:30:00Z"
        }
    """

    id: UUID = Field(..., description="Record UUID")
    dataset_id: UUID = Field(..., description="Parent dataset UUID")
    department_id: UUID | None = Field(None, description="Owning department UUID")
    payload: dict[str, Any] = Field(..., description="Record data")
    status: RecordStatus = Field(..., description="Record status")
    version: int = Field(..., description="Current version (optimistic lock)")
    created_by: UUID | None = Field(None, description="Creator user UUID")
    updated_by: UUID | None = Field(None, description="Last updater user UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}


class RecordListResponse(BaseModel):
    """Paginated list of records.
    
    Example:
        {
            "items": [...],
            "total": 150,
            "page": 1,
            "page_size": 20,
            "total_pages": 8
        }
    """

    items: list[DataRecordResponse] = Field(..., description="Records in current page")
    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


class RecordHistoryResponse(BaseModel):
    """Record version history.
    
    Example:
        {
            "record_id": "uuid-here",
            "versions": [...]
        }
    """

    record_id: UUID = Field(..., description="Record UUID")
    versions: list[RecordVersionResponse] = Field(..., description="Version history (newest first)")


# ============================================================================
# Submit Response (returned by POST/PATCH/DELETE)
# ============================================================================


class SubmitRecordResponse(BaseModel):
    """Response after submitting a record change.
    
    Phase 4: Auto-approval workflow
    - Returns version_id and state='applied' (immediately applied)
    - Also returns the applied record
    
    Phase 5: Real workflow
    - Returns version_id and state='pending'
    - record field will be None until approved
    
    Example:
        {
            "version_id": "uuid-here",
            "state": "applied",
            "record": {...}
        }
    """

    version_id: UUID = Field(..., description="RecordVersion UUID")
    state: RecordVersionState = Field(..., description="Current workflow state")
    record: DataRecordResponse | None = Field(
        None,
        description="Applied record (NULL if pending approval)",
    )
