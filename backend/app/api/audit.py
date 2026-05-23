"""Audit log API: read-only endpoint for browsing the immutable audit trail."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.deps import CurrentUser, require_perm
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


def _build_audit_response(entry: AuditLog) -> AuditLogResponse:
    """Build AuditLogResponse from AuditLog model.

    Note: relies on user being eager-loaded via selectinload in the query.
    """
    return AuditLogResponse(
        id=entry.id,
        tenant_id=str(entry.tenant_id) if entry.tenant_id else None,
        user_id=str(entry.user_id) if entry.user_id else None,
        user_email=entry.user.email if entry.user else None,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        detail=entry.detail or {},
        ip=str(entry.ip) if entry.ip else None,
        user_agent=entry.user_agent,
        created_at=entry.created_at.isoformat(),
    )


@router.get(
    "",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_perm("read", "audit_log"))],
)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    action: Annotated[str | None, Query(description="Filter by action verb")] = None,
    resource_type: Annotated[str | None, Query(description="Filter by resource type")] = None,
    user_id: Annotated[str | None, Query(description="Filter by acting user UUID")] = None,
    start_time: Annotated[
        datetime | None,
        Query(description="ISO 8601 start time (inclusive)"),
    ] = None,
    end_time: Annotated[
        datetime | None,
        Query(description="ISO 8601 end time (exclusive)"),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search in action, resource_type, resource_id"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    """List audit log entries scoped to the current tenant.

    Most recent first. Supports filtering by action, resource_type, user_id,
    and a time window. Eagerly loads the acting user so user_email can be
    populated without a per-row query.
    """
    # Base query: tenant-scoped + eager-load user for email
    base_filters = [AuditLog.tenant_id == user.tenant_id]

    if action:
        base_filters.append(AuditLog.action == action)
    if resource_type:
        base_filters.append(AuditLog.resource_type == resource_type)
    if user_id:
        base_filters.append(AuditLog.user_id == UUID(user_id))
    if start_time:
        # Normalize naive datetime to UTC if needed
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        base_filters.append(AuditLog.created_at >= start_time)
    if end_time:
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        base_filters.append(AuditLog.created_at < end_time)
    if search:
        like = f"%{search}%"
        base_filters.append(
            or_(
                AuditLog.action.ilike(like),
                AuditLog.resource_type.ilike(like),
                AuditLog.resource_id.ilike(like),
            )
        )

    # Count total
    count_stmt = select(sa.func.count()).select_from(AuditLog).where(*base_filters)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Fetch page (DESC by created_at, with user eager-loaded for email)
    stmt = (
        select(AuditLog)
        .where(*base_filters)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return AuditLogListResponse(
        logs=[_build_audit_response(e) for e in entries],
        total=total,
    )
