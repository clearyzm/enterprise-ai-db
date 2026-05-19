"""Seed global permissions

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12 10:10:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Global permissions (action, resource_type) — shared across all tenants
    # Based on 02-data-model.md §6 and 03-security.md §3.2-3.3
    permissions = [
        # Dataset permissions
        ("read", "dataset", "View dataset schema and metadata"),
        ("write", "dataset", "Create or modify dataset schema"),
        ("manage", "dataset", "Full dataset management including deletion"),
        # Record permissions
        ("read", "record", "View records"),
        ("write", "record", "Create or modify records (subject to approval)"),
        ("delete", "record", "Delete records (subject to approval)"),
        ("approve", "record", "Approve record changes in workflow"),
        # User management
        ("read", "user", "View user profiles"),
        ("manage", "user", "Create, modify, or disable users"),
        # Role management
        ("read", "role", "View roles and permissions"),
        ("manage", "role", "Create or modify roles and assign permissions"),
        # Department management
        ("read", "department", "View department structure"),
        ("manage", "department", "Create or modify departments"),
        # Workflow management
        ("read", "workflow", "View workflow definitions"),
        ("manage", "workflow", "Create or modify workflows"),
        # Tenant settings
        ("read", "tenant_settings", "View tenant configuration"),
        ("manage", "tenant_settings", "Modify tenant configuration"),
        # Audit log
        ("read", "audit_log", "View audit logs"),
        # AI query
        ("ai_query", "dataset", "Query AI assistant about dataset records"),
    ]

    # Insert with explicit UUID generation to ensure idempotency
    for action, resource_type, description in permissions:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (id, action, resource_type, description)
                VALUES (gen_random_uuid(), :action, :resource_type, :description)
                ON CONFLICT (action, resource_type) DO NOTHING
                """
            ).bindparams(
                action=action,
                resource_type=resource_type,
                description=description,
            )
        )


def downgrade() -> None:
    # Delete all seeded permissions
    # Note: This will cascade delete role_permissions entries
    op.execute("DELETE FROM permissions WHERE action IN ('read','write','delete','approve','manage','ai_query')")
