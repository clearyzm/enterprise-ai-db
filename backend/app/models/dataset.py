"""DataSet model — schema definition and configuration for structured data collections.

Each dataset defines:
- JSON Schema for payload validation
- UI configuration (column order, display settings)
- Business indexes for query optimization
- Default workflow for approval process
- AI indexing and sensitivity settings
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

import enum

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.department import Department
    from app.models.user import User
    # Forward references for Phase 4+
    # from app.models.workflow import Workflow
    # from app.models.record import DataRecord


class DataSetSensitivity(str, enum.Enum):
    """Data sensitivity levels for access control and AI indexing.
    
    Determines who can access the data and whether it's included in AI embeddings.
    """

    public = "public"  # Accessible to all users with read permission
    internal = "internal"  # Normal internal data (default)
    confidential = "confidential"  # Restricted to specific roles/departments
    restricted = "restricted"  # Highest sensitivity, minimal access


class DataSetStatus(str, enum.Enum):
    """Dataset lifecycle status."""

    active = "active"  # Normal active dataset
    archived = "archived"  # Read-only, no new records
    migrating = "migrating"  # Schema migration in progress


class DataSet(Base, TenantMixin, TimestampMixin):
    """DataSet — schema definition and configuration for data collections.
    
    Defines the structure, validation rules, and access policies for a collection
    of structured records. Each dataset has:
    - JSON Schema for payload validation
    - UI configuration for display and search
    - Business indexes for query optimization
    - Default workflow for approval process
    - Sensitivity level for access control
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        owner_dept_id: Owning department (nullable)
        name: Dataset name (unique per tenant)
        description: Human-readable description
        schema: JSON Schema for payload validation
        ui_config: UI display configuration (column order, visibility, searchability)
        indexes: Business field indexes configuration
        workflow_id: Default workflow for record changes (nullable, FK added in Phase 5)
        ai_indexed: Whether to create vector embeddings for AI search
        sensitivity: Data sensitivity level (public/internal/confidential/restricted)
        status: Dataset status (active/archived/migrating)
        created_by: User who created this dataset
    
    Relationships:
        tenant: Parent tenant
        owner_department: Owning department (nullable)
        creator: User who created this dataset
        # Phase 4+: records, workflow, chunks
    
    Example schema:
        {
            "type": "object",
            "required": ["order_no", "amount"],
            "properties": {
                "order_no": {"type": "string", "pattern": "^[A-Z]{2}\\d{8}$"},
                "amount": {"type": "number", "minimum": 0},
                "customer": {"type": "string", "maxLength": 200},
                "status": {"type": "string", "enum": ["draft", "paid", "cancelled"]},
                "_sensitivity": {"type": "string", "enum": ["internal", "confidential"]}
            },
            "additionalProperties": false
        }
    
    Example ui_config:
        {
            "columns": [
                {"field": "order_no", "label": "Order No.", "width": 120, "sortable": true},
                {"field": "amount", "label": "Amount", "width": 100, "format": "currency"},
                {"field": "customer", "label": "Customer", "width": 200, "searchable": true}
            ],
            "default_sort": {"field": "created_at", "order": "desc"},
            "row_actions": ["edit", "delete", "history"]
        }
    
    Example indexes:
        [
            {"field": "order_no", "unique": true},
            {"field": "customer", "type": "trigram"},
            {"fields": ["status", "created_at"], "type": "btree"}
        ]
    """

    __tablename__ = "data_sets"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Dataset UUID",
    )

    # tenant_id from TenantMixin

    owner_dept_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Owning department (nullable)",
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Dataset name (unique per tenant)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description",
    )

    schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="JSON Schema for payload validation",
    )

    ui_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="UI display configuration (columns, sorting, actions)",
    )

    indexes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        comment="Business field indexes configuration",
    )

    workflow_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        # ForeignKey("workflows.id", ondelete="SET NULL"),  # Added in Phase 5
        nullable=True,
        comment="Default workflow for record changes (Phase 5+)",
    )

    ai_indexed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("true"),
        comment="Whether to create vector embeddings for AI search",
    )

    sensitivity: Mapped[DataSetSensitivity] = mapped_column(
        sa.Enum(DataSetSensitivity, name="dataset_sensitivity_enum", create_type=False, native_enum=False),
        nullable=False,
        server_default="internal",
        index=True,
        comment="Data sensitivity level for access control",
    )

    status: Mapped[DataSetStatus] = mapped_column(
        sa.Enum(DataSetStatus, name="dataset_status_enum", create_type=False, native_enum=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Dataset lifecycle status",
    )

    created_by: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this dataset",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="datasets",
        lazy="joined",
    )

    owner_department: Mapped["Department | None"] = relationship(
        "Department",
        foreign_keys=[owner_dept_id],
        lazy="selectin",
    )

    creator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="selectin",
    )

    # Phase 4+ relationships (uncomment when models exist):
    # workflow: Mapped["Workflow | None"] = relationship(
    #     "Workflow",
    #     back_populates="datasets",
    #     lazy="selectin",
    # )
    #
    # records: Mapped[list["DataRecord"]] = relationship(
    #     "DataRecord",
    #     back_populates="dataset",
    #     lazy="noload",  # Don't auto-load records (can be thousands)
    #     cascade="all, delete-orphan",
    # )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_datasets_tenant_name"),
        CheckConstraint(
            "sensitivity IN ('public', 'internal', 'confidential', 'restricted')",
            name="ck_dataset_sensitivity",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'migrating')",
            name="ck_dataset_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<DataSet(id={self.id}, name='{self.name}', tenant_id={self.tenant_id}, sensitivity={self.sensitivity.value})>"
