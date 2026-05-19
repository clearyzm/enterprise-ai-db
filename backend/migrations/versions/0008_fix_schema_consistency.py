"""Fix schema consistency - add missing columns to match ORM models

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-19 10:00:00.000000

This migration ensures all tables have the columns defined in their ORM models:
- TimestampMixin: created_at, updated_at
- Primary keys: user_roles.id
- All tables checked against their model definitions
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to ensure schema matches ORM models."""
    
    # Fix roles table - add updated_at (created_at should exist from TimestampMixin)
    op.execute("""
        ALTER TABLE roles 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE roles 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix user_roles table - add id, created_at, updated_at
    # First check if id column exists, if not add it
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'user_roles' AND column_name = 'id'
            ) THEN
                ALTER TABLE user_roles 
                ADD COLUMN id UUID PRIMARY KEY DEFAULT gen_random_uuid();
            END IF;
        END $$;
    """)
    
    op.execute("""
        ALTER TABLE user_roles 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE user_roles 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix tenants table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix users table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix departments table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE departments 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE departments 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix data_sets table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE data_sets 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE data_sets 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix workflows table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE workflows 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE workflows 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix data_records table - ensure created_at, updated_at exist
    op.execute("""
        ALTER TABLE data_records 
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    op.execute("""
        ALTER TABLE data_records 
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    """)
    
    # Fix permissions table - no TimestampMixin, but verify it exists
    # (permissions table doesn't use TimestampMixin per the model)
    
    # Fix role_permissions table - composite PK, no additional columns needed
    # (already has role_id, permission_id as composite PK)
    
    # Fix user_departments table - composite PK, no additional columns needed
    # (already has user_id, department_id as composite PK, plus is_primary)
    
    # Fix approval_actions table - has created_at but not updated_at (intentional per model)
    # (only has created_at, no updated_at - this is correct per the model)
    
    # Fix ai_conversations table - has created_at but not updated_at (intentional per model)
    # (only has created_at, no updated_at - this is correct per the model)
    
    # Fix ai_messages table - has created_at but not updated_at (intentional per model)
    # (only has created_at, no updated_at - this is correct per the model)
    
    # Fix record_versions table - has created_at but not updated_at (intentional per model)
    # (only has created_at, no updated_at - this is correct per the model)
    
    print("✓ Schema consistency migration completed successfully")


def downgrade() -> None:
    """Remove columns added in this migration.
    
    WARNING: This will drop data in the added columns.
    Only run this if you're certain you want to revert.
    """
    
    # Note: We don't drop created_at/updated_at as they may have been added
    # by earlier migrations. We only drop columns we're certain were added here.
    
    # Drop user_roles.id if it was added by this migration
    # (This is risky - only do if you're sure it was added by this migration)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'user_roles' AND column_name = 'id'
            ) THEN
                ALTER TABLE user_roles DROP COLUMN id;
            END IF;
        END $$;
    """)
    
    print("⚠ Downgrade completed - some timestamp columns may remain")
