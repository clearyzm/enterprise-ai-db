"""Role and Permission models — RBAC implementation.

Permissions are global (shared across tenants).
Roles are tenant-specific and contain a set of permissions.
UserRoles assign roles to users with optional scope (department/dataset filtering).
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from app.models.base_model import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class Permission(Base):
    """Permission — global action + resource_type pair.
    
    Permissions are shared across all tenants (not tenant-scoped).
    Seeded in migration 0003_seed_permissions.py.
    
    Attributes:
        id: Primary key (UUID)
        action: Action name (read/write/delete/approve/manage/ai_query)
        resource_type: Resource type (tenant_settings/user/role/department/dataset/record/workflow/audit_log)
        description: Human-readable description
    
    Relationships:
        roles: Many-to-many via role_permissions
    """

    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Permission UUID",
    )

    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Action name (read/write/delete/approve/manage/ai_query)",
    )

    resource_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Resource type (tenant_settings/user/role/department/dataset/record/workflow/audit_log)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description",
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("action", "resource_type", name="uq_permissions_action_resource"),
    )

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, action='{self.action}', resource_type='{self.resource_type}')>"


class Role(Base, TenantMixin, TimestampMixin):
    """Role — tenant-specific collection of permissions.
    
    Roles are defined per tenant and contain a set of permissions.
    System roles (tenant_admin, editor, viewer, etc.) are seeded automatically.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        name: Role name (unique per tenant)
        description: Human-readable description
        is_system: Whether this is a system-defined role (cannot be deleted)
    
    Relationships:
        tenant: Parent tenant
        permissions: Many-to-many via role_permissions
        user_roles: Users assigned this role
    """

    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Role UUID",
    )

    # tenant_id from TenantMixin

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Role name (unique per tenant)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description",
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
        comment="Whether this is a system-defined role (cannot be deleted)",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="roles",
        lazy="joined",
    )

    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin",
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}', tenant_id={self.tenant_id})>"


class RolePermission(Base):
    """Association table for Role <-> Permission many-to-many relationship.
    
    Attributes:
        role_id: Foreign key to roles
        permission_id: Foreign key to permissions
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Role UUID",
    )

    permission_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Permission UUID",
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"


class UserRole(Base, TimestampMixin):
    """User role assignment with optional scope.
    
    Assigns a role to a user with optional scope filtering:
    - {} (empty): Full tenant access
    - {"department_id": "<uuid>"}: Limited to specific department
    - {"dataset_ids": ["<uuid>", ...]}: Limited to specific datasets
    - {"department_id": "...", "dataset_ids": [...]}: Intersection of both
    
    Attributes:
        id: Primary key (UUID)
        user_id: Foreign key to users
        role_id: Foreign key to roles
        scope: JSONB scope filter (empty = full tenant)
    
    Relationships:
        user: Associated user
        role: Associated role
    """

    __tablename__ = "user_roles"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="UserRole UUID",
    )

    user_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User UUID",
    )

    role_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Role UUID",
    )

    scope: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="Scope filter: {} = full tenant, {department_id: ...} = dept-scoped, {dataset_ids: [...]} = dataset-scoped",
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_roles",
        lazy="joined",
    )

    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="user_roles",
        lazy="joined",
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope", name="uq_user_roles_user_role_scope"),
    )

    def __repr__(self) -> str:
        return f"<UserRole(id={self.id}, user_id={self.user_id}, role_id={self.role_id}, scope={self.scope})>"
