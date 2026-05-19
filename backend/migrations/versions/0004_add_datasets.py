"""Add data_sets table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-12 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass

def downgrade() -> None:
    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON data_sets")
    
    # Disable RLS
    op.execute("ALTER TABLE data_sets DISABLE ROW LEVEL SECURITY")
    
    # Drop indexes
    op.drop_index("ix_datasets_status", table_name="data_sets")
    op.drop_index("ix_datasets_sensitivity", table_name="data_sets")
    op.drop_index("ix_datasets_owner_dept", table_name="data_sets")
    op.drop_index("ix_datasets_tenant", table_name="data_sets")
    
    # Drop table
    op.drop_table("data_sets")
    
    # Drop enums
    op.execute("DROP TYPE dataset_status_enum")
    op.execute("DROP TYPE dataset_sensitivity_enum")
