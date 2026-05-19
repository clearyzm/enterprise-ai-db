"""Base model with common fields and mixins for all ORM models.

Provides:
- TimestampMixin: created_at, updated_at (auto-managed)
- TenantMixin: tenant_id (for multi-tenant tables)
- SoftDeleteMixin: status field for soft deletion
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

import enum


class StatusEnum(str, enum.Enum):
    """Common status values for soft deletion."""

    active = "active"
    inactive = "inactive"
    soft_deleted = "soft_deleted"


class Base(DeclarativeBase):
    """Base class for all ORM models.
    
    All models inherit from this to register with SQLAlchemy metadata.
    """

    # Type annotation map for common Python types → SQL types
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        UUID: Uuid,
    }


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps.
    
    Usage:
        class User(Base, TimestampMixin):
            ...
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp",
    )


class TenantMixin:
    """Mixin for tenant_id foreign key.
    
    All multi-tenant tables must include this.
    RLS policies filter on tenant_id = current_setting('app.tenant_id')::uuid.
    
    Usage:
        class User(Base, TenantMixin, TimestampMixin):
            __tablename__ = "users"
            ...
    """

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant isolation key (RLS enforced)",
    )


class SoftDeleteMixin:
    """Mixin for soft deletion via status field.
    
    Usage:
        class Record(Base, SoftDeleteMixin):
            ...
        
        # Soft delete
        record.status = StatusEnum.soft_deleted
        
        # Query active only
        stmt = select(Record).where(Record.status == StatusEnum.active)
    """

    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum, name="status_enum", create_type=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Record status (active/inactive/soft_deleted)",
    )
