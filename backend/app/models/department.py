"""Department model — organizational hierarchy within a tenant.

Departments support tree structure (parent_id) and many-to-many relationship with users.
Used for permission scoping and data access control.
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class Department(Base, TenantMixin, TimestampMixin):
    """Department — organizational unit within a tenant.
    
    Supports hierarchical structure via parent_id (self-referential FK).
    Used for permission scoping: roles can be limited to specific departments.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        parent_id: Self-referential FK for tree structure (nullable)
        name: Department name (unique per tenant)
        code: Optional short code (e.g., 'FIN', 'SALES')
    
    Relationships:
        tenant: Parent tenant
        parent: Parent department (nullable)
        children: Child departments
        users: Many-to-many via user_departments
        user_departments: Association objects with is_primary flag
    """

    __tablename__ = "departments"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Department UUID",
    )

    # tenant_id from TenantMixin

    parent_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Parent department for hierarchical structure",
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Department name (unique per tenant)",
    )

    code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional short code (e.g., 'FIN', 'SALES')",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="departments",
        lazy="joined",
    )

    parent: Mapped["Department | None"] = relationship(
        "Department",
        remote_side=[id],
        back_populates="children",
        lazy="selectin",
    )

    children: Mapped[list["Department"]] = relationship(
        "Department",
        back_populates="parent",
        lazy="selectin",
        cascade="all",
    )

    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_departments",
        back_populates="departments",
        lazy="selectin",
    )

    user_departments: Mapped[list["UserDepartment"]] = relationship(
        "UserDepartment",
        back_populates="department",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_departments_tenant_name"),
    )

    def __repr__(self) -> str:
        return f"<Department(id={self.id}, name='{self.name}', tenant_id={self.tenant_id})>"


class UserDepartment(Base):
    """Association table for User <-> Department many-to-many relationship.
    
    Includes is_primary flag to mark a user's primary department.
    
    Attributes:
        user_id: Foreign key to users
        department_id: Foreign key to departments
        is_primary: Whether this is the user's primary department
    
    Relationships:
        user: Associated user
        department: Associated department
    """

    __tablename__ = "user_departments"

    user_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="User UUID",
    )

    department_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Department UUID",
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
        comment="Whether this is the user's primary department",
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_departments",
        lazy="joined",
    )

    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="user_departments",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<UserDepartment(user_id={self.user_id}, department_id={self.department_id}, is_primary={self.is_primary})>"
