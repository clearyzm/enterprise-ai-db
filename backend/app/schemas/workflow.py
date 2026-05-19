"""Workflow and ApprovalAction Pydantic schemas for API validation and serialization.

Provides:
- WorkflowCreate/Update/Response schemas
- ApprovalActionResponse schema
- Step configuration validation
- Approver configuration validation
"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# Step Configuration Schemas
# ============================================================================


class ApproverConfig(BaseModel):
    """Approver configuration for a workflow step.
    
    Types:
        - role: Any user with the specified role name
        - user_ids: List of specific user UUIDs
        - dept_head: Department head of the record's department
        - role_in_dept: Users with role in the record's department
    """

    type: Literal["role", "user_ids", "dept_head", "role_in_dept"] = Field(
        ...,
        description="Approver type",
    )
    value: str | list[UUID] | None = Field(
        None,
        description="Role name (for role/role_in_dept) or user UUID list (for user_ids)",
    )

    @model_validator(mode="after")
    def validate_value(self) -> "ApproverConfig":
        """Validate value based on type."""
        if self.type == "role" or self.type == "role_in_dept":
            if not isinstance(self.value, str) or not self.value:
                raise ValueError(f"type={self.type} requires non-empty string value")
        elif self.type == "user_ids":
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("type=user_ids requires non-empty list of UUIDs")
        elif self.type == "dept_head":
            if self.value is not None:
                raise ValueError("type=dept_head must have value=null")
        return self


class WorkflowStep(BaseModel):
    """Single step in a workflow.
    
    Attributes:
        name: Step display name
        approver: Approver configuration
        mode: 'any' (one approval) or 'all' (countersign)
        require_dept_match: Approver must be in same dept as record
        condition: Optional json-logic condition (evaluated against record_version)
    """

    name: str = Field(..., min_length=1, max_length=200, description="Step name")
    approver: ApproverConfig = Field(..., description="Approver configuration")
    mode: Literal["any", "all"] = Field(
        default="any",
        description="Approval mode: 'any' or 'all'",
    )
    require_dept_match: bool = Field(
        default=False,
        description="Approver must be in same department as record",
    )
    condition: dict[str, Any] | None = Field(
        default=None,
        description="Optional json-logic condition",
    )


# ============================================================================
# Workflow Schemas
# ============================================================================


class WorkflowBase(BaseModel):
    """Base workflow fields."""

    name: str = Field(..., min_length=1, max_length=200, description="Workflow name")
    description: str | None = Field(None, max_length=2000, description="Description")
    steps: list[WorkflowStep] = Field(
        default_factory=list,
        description="Workflow steps",
    )

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: list[WorkflowStep]) -> list[WorkflowStep]:
        """Validate steps array."""
        if len(v) > 20:
            raise ValueError("Maximum 20 steps allowed")
        return v


class WorkflowCreate(WorkflowBase):
    """Schema for creating a new workflow."""

    pass


class WorkflowUpdate(BaseModel):
    """Schema for updating an existing workflow.
    
    All fields optional for partial updates.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    steps: list[WorkflowStep] | None = Field(None)
    status: Literal["active", "archived"] | None = Field(None)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: list[WorkflowStep] | None) -> list[WorkflowStep] | None:
        """Validate steps array."""
        if v is not None and len(v) > 20:
            raise ValueError("Maximum 20 steps allowed")
        return v


class WorkflowResponse(WorkflowBase):
    """Schema for workflow API responses."""

    id: UUID
    tenant_id: UUID
    status: Literal["active", "archived"]
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowListItem(BaseModel):
    """Minimal workflow info for list endpoints."""

    id: UUID
    name: str
    description: str | None
    step_count: int = Field(..., description="Number of steps")
    status: Literal["active", "archived"]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_workflow(cls, workflow: Any) -> "WorkflowListItem":
        """Create from ORM Workflow model."""
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            step_count=len(workflow.steps),
            status=workflow.status.value,
            created_at=workflow.created_at,
        )


# ============================================================================
# Approval Action Schemas
# ============================================================================


class ApprovalActionResponse(BaseModel):
    """Schema for approval action API responses."""

    id: UUID
    tenant_id: UUID
    version_id: UUID
    step_index: int
    approver_id: UUID
    approver_email: str | None = Field(None, description="Approver email (joined)")
    approver_name: str | None = Field(None, description="Approver name (joined)")
    action: Literal["approve", "reject"]
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalActionCreate(BaseModel):
    """Schema for creating an approval action (approve/reject)."""

    comment: str | None = Field(
        None,
        max_length=2000,
        description="Optional comment from approver",
    )


# ============================================================================
# Approval Inbox/Outbox Schemas
# ============================================================================


class ApprovalInboxItem(BaseModel):
    """Single item in approval inbox (pending versions awaiting my approval)."""

    version_id: UUID
    record_id: UUID | None
    dataset_id: UUID
    dataset_name: str
    op: Literal["insert", "update", "delete"]
    current_step: int
    step_name: str
    workflow_name: str
    proposed_by_id: UUID
    proposed_by_email: str | None
    proposed_by_name: str | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalOutboxItem(BaseModel):
    """Single item in approval outbox (versions I submitted)."""

    version_id: UUID
    record_id: UUID | None
    dataset_id: UUID
    dataset_name: str
    op: Literal["insert", "update", "delete"]
    state: Literal["pending", "approved", "rejected", "applied", "superseded", "cancelled"]
    current_step: int | None = Field(None, description="Current step (null if not pending)")
    step_name: str | None = Field(None, description="Current step name")
    workflow_name: str | None
    reject_reason: str | None
    created_at: datetime
    applied_at: datetime | None

    model_config = {"from_attributes": True}


# ============================================================================
# Approval Detail Schema
# ============================================================================


class ApprovalDetail(BaseModel):
    """Detailed approval information including version data and diff."""

    version_id: UUID
    record_id: UUID | None
    dataset_id: UUID
    dataset_name: str
    op: Literal["insert", "update", "delete"]
    state: Literal["pending", "approved", "rejected", "applied", "superseded", "cancelled"]
    before_payload: dict[str, Any] | None
    after_payload: dict[str, Any] | None
    current_step: int
    workflow_id: UUID | None
    workflow_name: str | None
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    proposed_by_id: UUID
    proposed_by_email: str | None
    proposed_by_name: str | None
    reason: str | None
    reject_reason: str | None
    created_at: datetime
    applied_at: datetime | None
    actions: list[ApprovalActionResponse] = Field(
        default_factory=list,
        description="Approval actions taken so far",
    )

    model_config = {"from_attributes": True}


# ============================================================================
# Pagination
# ============================================================================


class PaginatedWorkflows(BaseModel):
    """Paginated workflow list response."""

    items: list[WorkflowListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedApprovals(BaseModel):
    """Paginated approval list response."""

    items: list[ApprovalInboxItem] | list[ApprovalOutboxItem]
    total: int
    page: int
    page_size: int
    total_pages: int
