"""Add data_records and record_versions tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass
def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON record_versions")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON data_records")
    
    # Disable RLS
    op.execute("ALTER TABLE record_versions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_records DISABLE ROW LEVEL SECURITY")
    
    # Drop indexes for record_versions
    op.execute("DROP INDEX IF EXISTS ix_rv_record_created")
    op.execute("DROP INDEX IF EXISTS ix_rv_tenant_pending")
    op.drop_index("ix_rv_state", table_name="record_versions")
    op.drop_index("ix_rv_dataset", table_name="record_versions")
    op.drop_index("ix_rv_record", table_name="record_versions")
    
    # Drop record_versions table
    op.drop_table("record_versions")
    
    # Drop indexes for data_records
    op.execute("DROP INDEX IF EXISTS ix_records_tenant_dept_active")
    op.execute("DROP INDEX IF EXISTS ix_records_tenant_dataset_active")
    op.drop_index("ix_records_status", table_name="data_records")
    op.drop_index("ix_records_department", table_name="data_records")
    op.drop_index("ix_records_dataset", table_name="data_records")
    
    # Drop data_records table
    op.drop_table("data_records")
    
    # Drop enums
    op.execute("DROP TYPE record_version_state_enum")
    op.execute("DROP TYPE record_version_op_enum")
    op.execute("DROP TYPE record_status_enum")
