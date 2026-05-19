"""Fix approval_actions and workflows table schema

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-19 11:00:00.000000

Fixes:
1. Rename approval_actions.decision → action (to match ORM model)
2. Add workflows.status, created_by, updated_at (to match ORM model)
3. Update CHECK constraint name for approval_actions
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply schema fixes for approval_actions and workflows tables."""
    
    # Fix 1: approval_actions.decision → action
    op.execute("ALTER TABLE approval_actions RENAME COLUMN decision TO action")
    
    # Drop old CHECK constraint (if exists)
    op.execute("ALTER TABLE approval_actions DROP CONSTRAINT IF EXISTS ck_approval_action_type")
    
    # Recreate CHECK constraint with correct column name
    op.execute("""
        ALTER TABLE approval_actions 
        ADD CONSTRAINT ck_approval_action_type 
        CHECK (action IN ('approve', 'reject'))
    """)
    
    # Fix 2: workflows table - add status, created_by, updated_at
    op.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")
    
    # Add CHECK constraint for status
    op.execute("""
        ALTER TABLE workflows 
        ADD CONSTRAINT ck_workflow_status 
        CHECK (status IN ('active', 'archived'))
    """)
    
    # Add created_by column
    op.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id) ON DELETE SET NULL")
    
    # Add updated_at column
    op.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    
    # Create index on status for filtering
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflows_status ON workflows(status)")


def downgrade() -> None:
    """Revert schema fixes."""
    
    # Revert workflows changes
    op.execute("DROP INDEX IF EXISTS ix_workflows_status")
    op.execute("ALTER TABLE workflows DROP CONSTRAINT IF EXISTS ck_workflow_status")
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE workflows DROP COLUMN IF EXISTS status")
    
    # Revert approval_actions changes
    op.execute("ALTER TABLE approval_actions DROP CONSTRAINT IF EXISTS ck_approval_action_type")
    op.execute("ALTER TABLE approval_actions RENAME COLUMN action TO decision")
    op.execute("""
        ALTER TABLE approval_actions 
        ADD CONSTRAINT ck_approval_action_type 
        CHECK (decision IN ('approve', 'reject'))
    """)
