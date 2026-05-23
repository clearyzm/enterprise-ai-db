"""Audit log writer service.

Provides a single `log_event` async helper that other services and API endpoints
call to record security-relevant actions. Designed to:
- Never block the calling code on failure (audit write failures are logged but
  do not raise — losing one audit record is preferable to failing the actual
  business operation).
- Run inside the caller's existing AsyncSession (caller handles commit). This
  keeps audit writes atomic with the operation they audit.
- Accept optional context (IP, user-agent, structured detail dict).

Usage example (inside any service that mutates state):

    from app.services.audit_service import log_event

    await log_event(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="create_record",
        resource_type="record",
        resource_id=str(new_record.id),
        detail={"dataset_id": str(ds_id), "values_keys": list(values.keys())},
    )
    # caller continues with await db.commit() as part of their normal flow
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession,
    *,
    tenant_id: UUID | str | None,
    user_id: UUID | str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Record an audit event in the caller's transaction.

    Failures are logged but never raised — audit writes are best-effort and
    must not break the underlying business operation.

    Args:
        db: Caller's existing AsyncSession (this function will NOT commit).
        tenant_id: Tenant scope, or None for cross-tenant system events.
        user_id: Acting user, or None for unauthenticated/system events.
        action: Verb like "create_record" / "approve" / "login".
        resource_type: Resource category like "record" / "approval" / "user".
        resource_id: Stringified ID of the affected resource (optional).
        detail: JSON-serializable extra context (will become JSONB).
        ip: Client IP address.
        user_agent: Client User-Agent string.
    """
    try:
        entry = AuditLog(
            tenant_id=tenant_id if isinstance(tenant_id, UUID) or tenant_id is None
                else UUID(str(tenant_id)),
            user_id=user_id if isinstance(user_id, UUID) or user_id is None
                else UUID(str(user_id)),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail or {},
            ip=ip,
            user_agent=user_agent,
        )
        db.add(entry)
        # Note: caller is responsible for await db.commit().
        # We use db.add() not flush — letting the caller batch the write with
        # their existing transaction is more efficient and keeps audit + business
        # write atomic.
    except Exception as exc:
        # Never let an audit failure break the business operation.
        logger.warning(
            "audit_log_write_failed action=%s resource_type=%s resource_id=%s err=%s",
            action,
            resource_type,
            resource_id,
            exc,
        )
