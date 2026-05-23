"""AuditLog model: immutable audit trail for tenant-scoped user actions.

The audit_log table records security-relevant events (data changes, approvals,
logins, etc.) for compliance and forensics. Records are insert-only — they are
never updated or deleted via the application layer. The schema was created in
migrations/versions/0001_init.py; this model maps to that pre-existing table.

Key design notes:
- id is bigserial (BigInteger autoincrement) — audit logs are high-volume and
  monotonic ints are cheaper to write/index than UUIDs.
- tenant_id is nullable with ON DELETE SET NULL — tenant deletion preserves
  the audit trail. (Differs from TenantMixin which forces NOT NULL + CASCADE.)
- No updated_at, no deleted_at — audit records are immutable.
- resource_id is text (not UUID) — supports heterogeneous resource identifiers.
- ip uses PostgreSQL INET type, detail uses JSONB.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class AuditLog(Base):
    """Immutable audit log entry.

    Attributes:
        id: Auto-incrementing bigint primary key.
        tenant_id: Tenant this event belongs to (nullable to preserve logs across tenant deletion).
        user_id: Actor user (nullable for system events / unauthenticated attempts).
        action: Free-text action verb (e.g. "create_record", "approve", "reject", "login").
        resource_type: Resource category (e.g. "record", "approval", "user", "role", "dataset").
        resource_id: Identifier of the affected resource (text for flexibility; usually UUID or numeric).
        detail: JSONB payload with operation-specific context (diff, status changes, etc.).
        ip: Client IP address (PostgreSQL INET, supports IPv4 and IPv6).
        user_agent: Client User-Agent string.
        created_at: When the event happened. Set by DB default, never modified.

    Relationships:
        tenant: The tenant scope (nullable).
        user: The acting user (nullable).
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Auto-incrementing bigint PK",
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Tenant scope (nullable to preserve audit on tenant deletion)",
    )

    user_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Actor user (nullable for system or unauthenticated events)",
    )

    action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Action verb, e.g. 'create_record', 'approve', 'login'",
    )

    resource_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Resource category, e.g. 'record', 'approval', 'user'",
    )

    resource_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Affected resource identifier (text for flexibility)",
    )

    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        comment="Operation-specific JSON payload",
    )

    ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        comment="Client IP (IPv4 or IPv6)",
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Client User-Agent string",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
        comment="Event timestamp (immutable)",
    )

    # ------------------------------------------------------------------
    # Relationships (read-only; audit logs are inserted with raw IDs,
    # but reading via relationship is useful for the API layer)
    # ------------------------------------------------------------------

    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        foreign_keys=[tenant_id],
        lazy="joined",
    )

    user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"resource_type={self.resource_type!r} resource_id={self.resource_id!r}>"
        )
