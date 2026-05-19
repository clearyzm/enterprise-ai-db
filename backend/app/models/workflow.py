"""Workflow and ApprovalAction models — approval workflow configuration and audit trail.

Workflow:
- Defines multi-step approval process for dataset changes
- Each step specifies approvers (role/user_ids/dept_head/role_in_dept)
- Supports conditional steps via json-logic
- Mode: 'any' (one approver) or 'all' (all approvers must approve)

ApprovalAction:
- Audit trail of approve/reject actions
- Unique constraint prevents duplicate approvals
- Links to record_version and workflow step
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

import enum

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.record import RecordVersion


# Built-in auto-approve workflow ID (constant UUID)
AUTO_APPROVE_WORKFLOW_ID = UUID("00000000-0000-0000-0000-000000000001")


class WorkflowStatus(str, enum.Enum):
    """Workflow lifecycle status."""

    active = "active"
    archived = "archived"


class ApprovalActionType(str, enum.Enum):
    """Type of approval action."""

    approve = "approve"
    reject = "reject"


class Workflow(Base, TenantMixin, TimestampMixin):
    """Workflow — multi-step approval process configuration.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        name: Workflow name (unique per tenant)
        description: Human-readable description
        steps: Array of step configurations (JSONB)
        status: Workflow status (active/archived)
        created_by: User who created this workflow
    
    Step configuration schema:
        [
            {
                "name": "Manager Approval",
                "approver": {
                    "type": "role",              # role | user_ids | dept_head | role_in_dept
                    "value": "manager"           # role name | user UUID array | null
                },
                "mode": "any",                   # any | all
                "require_dept_match": true,      # approver must be in same dept as record
                "condition": {                   # optional json-logic condition
                    ">=": [{"var": "payload.amount"}, 10000]
                }
            },
            {
                "name": "Finance Review",
                "approver": {
                    "type": "role",
                    "value": "finance_reviewer"
                },
                "mode": "all",
                "condition": {
                    ">": [{"var": "payload.amount"}, 100000]
                }
            }
        ]
    
    Approver types:
        - role: Any user with the specified role
        - user_ids: Specific list of user UUIDs
        - dept_head: Department head of the record's department
        - role_in_dept: Users with role in the record's department
    
    Mode:
        - any: One approver approval advances to next step
        - all: All candidate approvers must approve (countersign)
    
    Condition:
        - Optional json-logic expression evaluated against record_version
        - If condition fails, step is skipped
        - Variables: payload (after_payload), op, proposed_by, etc.
    """

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Workflow UUID",
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Workflow name (unique per tenant)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description",
    )

    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        comment="Array of step configurations",
    )

    status: Mapped[WorkflowStatus] = mapped_column(
        sa.Enum(WorkflowStatus, name="workflow_status_enum", create_type=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Workflow status",
    )

    created_by: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Creator user",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    creator: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_workflow_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name='{self.name}', steps={len(self.steps)})>"


class ApprovalAction(Base, TenantMixin):
    """ApprovalAction — audit trail of approval/rejection actions.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        version_id: Foreign key to record_versions
        step_index: Workflow step index (0-based)
        approver_id: User who performed the action
        action: Action type (approve/reject)
        comment: Optional comment from approver
        created_at: Timestamp when action was performed
    
    Constraints:
        - Unique (version_id, step_index, approver_id) prevents duplicate approvals
        - step_index must be non-negative
    """

    __tablename__ = "approval_actions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Action UUID",
    )

    version_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("record_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Target record version",
    )

    step_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Workflow step index (0-based)",
    )

    approver_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Approver user",
    )

    action: Mapped[ApprovalActionType] = mapped_column(
        sa.Enum(ApprovalActionType, name="approval_action_type_enum", create_type=False),
        nullable=False,
        comment="Action type (approve/reject)",
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional comment from approver",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        comment="Action timestamp",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    version: Mapped["RecordVersion"] = relationship(
        "RecordVersion",
        foreign_keys=[version_id],
        lazy="selectin",
    )
    approver: Mapped["User"] = relationship(
        "User",
        foreign_keys=[approver_id],
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "step_index",
            "approver_id",
            name="uq_approval_version_step_approver",
        ),
        CheckConstraint("step_index >= 0", name="ck_approval_step_nonnegative"),
        CheckConstraint(
            "action IN ('approve', 'reject')",
            name="ck_approval_action_type",
        ),
        sa.Index("ix_approval_version_step", "version_id", "step_index"),
    )

    def __repr__(self) -> str:
        return f"<ApprovalAction(id={self.id}, version_id={self.version_id}, step={self.step_index}, action={self.action.value})>"
