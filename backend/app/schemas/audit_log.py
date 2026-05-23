"""Pydantic schemas for audit log API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    """Single audit log entry returned by the API."""

    id: int
    tenant_id: str | None
    user_id: str | None
    user_email: str | None = Field(
        default=None,
        description="Denormalized actor email for display (joined from users table)",
    )
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict[str, Any]
    ip: str | None
    user_agent: str | None
    created_at: str


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""

    logs: list[AuditLogResponse]
    total: int
