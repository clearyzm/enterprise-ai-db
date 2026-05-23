"""Extend RLS to remaining tenant-scoped tables.

Phase 5.A complete: 0010 covered 5 core tenant tables (users, departments,
data_sets, data_records, record_versions). This migration extends RLS to
the remaining tenant-scoped tables identified during Phase 5 review:

- chunks: vector index for AI retrieval — without RLS, AI tool layer
  could leak cross-tenant data even with PermissionService filtering at
  the orchestrator layer.
- ai_conversations, ai_messages: multi-tenant chat history.
- workflows, approval_actions: approval flow config and audit trail.
- roles: tenant-scoped custom roles (system roles have tenant_id=NULL
  and are unaffected by the policy).
- refresh_tokens: JWT refresh tokens, must never cross tenants.

Excluded tables (intentional):
- tenants, audit_log, permissions, role_permissions, user_roles,
  user_departments, alembic_version (see SECURITY.md for rationale).

Each table uses the same tenant_isolation policy as 0010:
  USING (tenant_id::text = current_setting('app.tenant_id', true))
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


# Tables to extend RLS to. All have a non-nullable tenant_id column.
ADDITIONAL_TENANT_SCOPED_TABLES = [
    "chunks",
    "ai_conversations",
    "ai_messages",
    "workflows",
    "approval_actions",
    "roles",
    "refresh_tokens",
]


def upgrade() -> None:
    for table in ADDITIONAL_TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id::text = current_setting('app.tenant_id', true));"
        )


def downgrade() -> None:
    for table in ADDITIONAL_TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
