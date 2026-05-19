"""User model — authentication and authorization principal.

Each user belongs to one tenant and can have multiple roles with different scopes.
RLS policies filter users by tenant_id.
"""
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

import enum

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.department import Department, UserDepartment
    from app.models.role import UserRole


class UserStatus(str, enum.Enum):
    """User account status."""

    active = "active"  # Normal active user
    disabled = "disabled"  # Temporarily disabled (can be re-enabled)
    invited = "invited"  # Invitation sent, not yet accepted


class User(Base, TenantMixin, TimestampMixin):
    """User — authentication and authorization principal.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        email: Email address (case-insensitive, unique per tenant)
        password_hash: Argon2id hash (nullable for SSO users in v2)
        display_name: User's display name
        status: Account status (active/disabled/invited)
        is_tenant_admin: Superuser flag within tenant (bypasses all permission checks)
        last_login_at: Last successful login timestamp
    
    Relationships:
        tenant: Parent tenant
        departments: Many-to-many via user_departments
        user_departments: Association objects with is_primary flag
        user_roles: Roles assigned to this user with scope
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="User UUID",
    )

    # tenant_id from TenantMixin

    email: Mapped[str] = mapped_column(
        CITEXT,
        nullable=False,
        comment="Email address (case-insensitive, unique per tenant)",
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Argon2id password hash (nullable for SSO users in v2)",
    )

    display_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="User's display name",
    )

    status: Mapped[UserStatus] = mapped_column(
        sa.Enum(UserStatus, name="user_status_enum", create_type=False),
        nullable=False,
        server_default="active",
        index=True,
        comment="Account status (active/disabled/invited)",
    )

    is_tenant_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
        comment="Superuser flag within tenant (bypasses all permission checks)",
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Last successful login timestamp",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="users",
        lazy="joined",  # Always load tenant with user
    )

    departments: Mapped[list["Department"]] = relationship(
        "Department",
        secondary="user_departments",
        back_populates="users",
        lazy="selectin",
    )

    user_departments: Mapped[list["UserDepartment"]] = relationship(
        "UserDepartment",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint(
            "status IN ('active', 'disabled', 'invited')",
            name="ck_user_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', tenant_id={self.tenant_id})>"
