"""enable row-level security on core tenant-scoped tables

This migration fixes the gap left by 0002_rls.py (whose upgrade body was an
empty `pass`). It enables PostgreSQL Row-Level Security and creates a
tenant_isolation policy on the 7 most critical tenant-scoped tables, ensuring
database-layer enforcement of multi-tenant boundaries.

Policy contract:
  - Every read/write to these tables is filtered by current_setting('app.tenant_id').
  - The application layer is expected to SET LOCAL app.tenant_id = '<uuid>' at
    the start of each request (already done via TenantContextMiddleware).
  - FORCE ROW LEVEL SECURITY is applied so even the table owner (postgres user)
    cannot bypass the policy. This is critical because the app connects as
    postgres, which would otherwise skip RLS by default.

Tables in this migration (5):
  - users
  - departments
  - data_sets
  - data_records
  - record_versions

Tables intentionally excluded:
  - tenants:    Chicken-and-egg with login flow (login must query tenants
                table before tenant_id is known). Tenant slug is public-key
                anyway; tenant_id isolation is enforced at app layer for
                this table.
  - audit_log:  Allows tenant_id = NULL for system events (e.g. login by
                user before tenant resolved). RLS would hide these rows.
  - user_roles, roles, workflows, approval_actions, refresh_tokens, ai_*, chunks:
                deferred to a follow-up migration after the 5 core tables
                are validated.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-22 13:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables with a standard tenant_id column
TENANT_SCOPED_TABLES = [
    "users",
    "departments",
    "data_sets",
    "data_records",
    "record_versions",
]


def upgrade() -> None:
    # Standard tenant_id-scoped tables
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id::text = current_setting('app.tenant_id', true));"
        )


def downgrade() -> None:
    # Reverse order: drop policies, disable RLS
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
