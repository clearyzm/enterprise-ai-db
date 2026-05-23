"""Tenant model — top-level isolation boundary.

Each tenant represents an independent organization with its own users, data, and settings.
RLS policies enforce tenant_id filtering on all child tables.
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

import enum

from app.models.base_model import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.department import Department
    from app.models.dataset import DataSet
    from app.models.role import Role


class TenantStatus(str, enum.Enum):
    """Tenant lifecycle status."""

    active = "active"
    suspended = "suspended"  # Billing issue or policy violation
    archived = "archived"  # Soft-deleted, data retained for compliance


class Tenant(Base, TimestampMixin):
    """Tenant — organization-level isolation.
    
    Attributes:
        id: Primary key (UUID)
        slug: URL-safe unique identifier (e.g., 'acme-corp')
        name: Display name (e.g., 'Acme Corporation')
        status: Lifecycle status (active/suspended/archived)
        ai_profile: AI behavior settings (JSONB)
            Example: {"temperature": 0.7, "max_tokens": 2000, "guardrail_level": "strict"}
        settings: General tenant settings (JSONB)
            Example: {"timezone": "UTC", "locale": "en-US", "quota": {"users": 100}}
    
    Relationships:
        users: All users belonging to this tenant
        departments: All departments in this tenant
        roles: All roles defined for this tenant
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Tenant UUID",
    )

    slug: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe unique identifier (e.g., 'acme-corp')",
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Display name (e.g., 'Acme Corporation')",
    )

    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status_enum", create_type=False, native_enum=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Lifecycle status (active/suspended/archived)",
    )

    ai_profile: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="AI behavior settings (temperature, max_tokens, guardrail_level, etc.)",
    )

    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="General tenant settings (timezone, locale, quota, etc.)",
    )

    # Relationships (lazy='selectin' for common access patterns)
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    departments: Mapped[list["Department"]] = relationship(
        "Department",
        back_populates="tenant",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    roles: Mapped[list["Role"]] = relationship(
        "Role",
        back_populates="tenant",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    datasets: Mapped[list["DataSet"]] = relationship(
        "DataSet",
        back_populates="tenant",
        lazy="noload",  # Don't auto-load datasets (can be many)
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name="ck_tenant_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug='{self.slug}', status={self.status.value})>"
