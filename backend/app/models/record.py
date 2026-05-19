"""DataRecord and RecordVersion models — structured data with approval workflow.

DataRecord:
- Stores the current active version of a record
- Includes optimistic locking via version field
- Soft deletion via status field

RecordVersion:
- Tracks all proposed changes (insert/update/delete)
- Approval workflow state machine
- Historical audit trail
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

import enum

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.dataset import DataSet
    from app.models.department import Department
    from app.models.user import User


class RecordStatus(str, enum.Enum):
    """DataRecord lifecycle status."""

    active = "active"
    soft_deleted = "soft_deleted"


class RecordVersionOp(str, enum.Enum):
    """Type of operation proposed in a record version."""

    insert = "insert"
    update = "update"
    delete = "delete"


class RecordVersionState(str, enum.Enum):
    """Approval workflow state for record versions."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"
    superseded = "superseded"
    cancelled = "cancelled"


class DataRecord(Base, TenantMixin, TimestampMixin):
    """DataRecord — current active version of a structured data record.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        dataset_id: Foreign key to data_sets
        department_id: Owning department (nullable)
        payload: JSONB data (validated against dataset.schema)
        status: Record status (active/soft_deleted)
        version: Optimistic lock version (incremented on each update)
        created_by: User who created this record
        updated_by: User who last updated this record
    """

    __tablename__ = "data_records"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Record UUID",
    )

    dataset_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("data_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent dataset",
    )

    department_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Owning department",
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="JSONB data",
    )

    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, name="record_status_enum", create_type=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Record status",
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("1"),
        comment="Optimistic lock version",
    )

    created_by: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Creator user",
    )

    updated_by: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Last updater",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    dataset: Mapped["DataSet"] = relationship("DataSet", lazy="selectin")
    department: Mapped["Department | None"] = relationship(
        "Department", foreign_keys=[department_id], lazy="selectin"
    )
    creator: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin"
    )
    updater: Mapped["User | None"] = relationship(
        "User", foreign_keys=[updated_by], lazy="selectin"
    )
    versions: Mapped[list["RecordVersion"]] = relationship(
        "RecordVersion",
        back_populates="record",
        lazy="noload",
        cascade="all, delete-orphan",
        order_by="RecordVersion.created_at.desc()",
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'soft_deleted')", name="ck_record_status"),
        CheckConstraint("version >= 1", name="ck_record_version_positive"),
        sa.Index(
            "ix_records_tenant_dataset_active",
            "tenant_id",
            "dataset_id",
            postgresql_where=sa.text("status = 'active'"),
        ),
        sa.Index(
            "ix_records_tenant_dept_active",
            "tenant_id",
            "department_id",
            postgresql_where=sa.text("status = 'active'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<DataRecord(id={self.id}, dataset_id={self.dataset_id}, version={self.version})>"


class RecordVersion(Base, TenantMixin):
    """RecordVersion — proposed change with approval workflow state.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        record_id: Foreign key to data_records (NULL for insert until applied)
        dataset_id: Foreign key to data_sets
        op: Operation type (insert/update/delete)
        before_payload: Payload before change (NULL for insert)
        after_payload: Payload after change (NULL for delete)
        state: Workflow state (pending/approved/rejected/applied/superseded/cancelled)
        workflow_id: Workflow used for approval (Phase 5+)
        current_step: Current workflow step index (Phase 5+)
        proposed_by: User who proposed this change
        applied_at: Timestamp when applied to data_records
        reason: User-provided reason for change
        reject_reason: Approver-provided reason for rejection
        created_at: Timestamp when version was created
    """

    __tablename__ = "record_versions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Version UUID",
    )

    record_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("data_records.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Target record",
    )

    dataset_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("data_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent dataset",
    )

    op: Mapped[RecordVersionOp] = mapped_column(
        sa.Enum(RecordVersionOp, name="record_version_op_enum", create_type=False),
        nullable=False,
        comment="Operation type",
    )

    before_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Payload before change",
    )

    after_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Payload after change",
    )

    state: Mapped[RecordVersionState] = mapped_column(
        sa.Enum(RecordVersionState, name="record_version_state_enum", create_type=False),
        nullable=False,
        server_default="pending",
        index=True,
        comment="Workflow state",
    )

    workflow_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        nullable=True,
        comment="Workflow ID (Phase 5+)",
    )

    current_step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=sa.text("0"),
        comment="Current workflow step",
    )

    proposed_by: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Proposer user",
    )

    applied_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Applied timestamp",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Change reason",
    )

    reject_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Rejection reason",
    )

    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="Workflow metadata (candidate snapshots, etc.)",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        comment="Creation timestamp",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    record: Mapped["DataRecord | None"] = relationship(
        "DataRecord", back_populates="versions", lazy="selectin"
    )
    dataset: Mapped["DataSet"] = relationship("DataSet", lazy="selectin")
    proposer: Mapped["User"] = relationship(
        "User", foreign_keys=[proposed_by], lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("op IN ('insert', 'update', 'delete')", name="ck_version_op"),
        CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'applied', 'superseded', 'cancelled')",
            name="ck_version_state",
        ),
        CheckConstraint("current_step >= 0", name="ck_version_step_nonnegative"),
        CheckConstraint(
            "(op = 'insert' AND before_payload IS NULL) OR (op != 'insert')",
            name="ck_version_insert_no_before",
        ),
        CheckConstraint(
            "(op = 'delete' AND after_payload IS NULL) OR (op != 'delete')",
            name="ck_version_delete_no_after",
        ),
        sa.Index(
            "ix_rv_tenant_pending",
            "tenant_id",
            "state",
            postgresql_where=sa.text("state = 'pending'"),
        ),
        sa.Index("ix_rv_record_created", "record_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<RecordVersion(id={self.id}, op={self.op.value}, state={self.state.value})>"
