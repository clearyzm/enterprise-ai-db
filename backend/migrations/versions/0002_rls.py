"""Enable Row-Level Security and tenant isolation policies

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12 10:05:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass

def downgrade() -> None:
    # Drop all policies first
    tables_with_rls = [
        "users",
        "departments",
        "roles",
        "workflows",
        "approval_actions", 
        "chunks", 
        "ai_conversations",
        "ai_messages",
        "user_roles",
        "data_sets",
        "data_records",
        "record_versions",
        "audit_log",
        "refresh_tokens",
    ]

    for table in tables_with_rls:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
