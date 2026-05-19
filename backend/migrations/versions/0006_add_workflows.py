"""Add workflows and approval_actions tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-12 16:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass

def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON approval_actions")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workflows")
    
    # Disable RLS
    op.execute("ALTER TABLE approval_actions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workflows DISABLE ROW LEVEL SECURITY")
    
    # Drop foreign keys
    op.drop_constraint("fk_record_versions_workflow", "record_versions", type_="foreignkey")
    op.drop_constraint("fk_datasets_workflow", "data_sets", type_="foreignkey")
    
    # Drop indexes
    op.drop_index("ix_approval_version_step", "approval_actions")
    op.drop_index("ix_approval_approver_id", "approval_actions")
    op.drop_index("ix_approval_version_id", "approval_actions")
    op.drop_index("ix_workflows_status", "workflows")
    op.drop_index("ix_workflows_tenant_id", "workflows")
    
    # Drop tables
    op.drop_table("approval_actions")
    op.drop_table("workflows")
    
    # Drop enums
    op.execute("DROP TYPE approval_action_type_enum")
    op.execute("DROP TYPE workflow_status_enum")
