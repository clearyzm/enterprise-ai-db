"""Initial schema — tenants, users, departments, roles, datasets, records

Revision ID: 0001
Revises: 
Create Date: 2026-05-12 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ EXTENSIONS ============
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')  # for users.email

    # ============ TENANTS ============
    op.execute("""
        CREATE TABLE tenants (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          slug            text UNIQUE NOT NULL,
          name            text NOT NULL,
          status          text NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','suspended','archived')),
          ai_profile      jsonb NOT NULL DEFAULT '{}'::jsonb,
          settings        jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at      timestamptz NOT NULL DEFAULT now(),
          updated_at      timestamptz NOT NULL DEFAULT now()
        )
    """)

    # ============ USERS ============
    op.execute("""
        CREATE TABLE users (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          email           citext NOT NULL,
          password_hash   text NOT NULL,
          display_name    text NOT NULL,
          status          text NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','disabled','invited')),
          is_tenant_admin boolean NOT NULL DEFAULT false,
          last_login_at   timestamptz,
          created_at      timestamptz NOT NULL DEFAULT now(),
          updated_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, email)
        )
    """)
    op.execute("CREATE INDEX ix_users_tenant ON users(tenant_id)")

    # ============ DEPARTMENTS ============
    op.execute("""
        CREATE TABLE departments (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          parent_id       uuid REFERENCES departments(id) ON DELETE SET NULL,
          name            text NOT NULL,
          code            text,
          created_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, name)
        )
    """)
    op.execute("CREATE INDEX ix_dept_tenant_parent ON departments(tenant_id, parent_id)")

    op.execute("""
        CREATE TABLE user_departments (
          user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          department_id   uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
          is_primary      boolean NOT NULL DEFAULT false,
          PRIMARY KEY (user_id, department_id)
        )
    """)

    # ============ ROLES & PERMISSIONS ============
    op.execute("""
        CREATE TABLE permissions (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          action          text NOT NULL,
          resource_type   text NOT NULL,
          description     text,
          UNIQUE (action, resource_type)
        )
    """)

    op.execute("""
        CREATE TABLE roles (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          name            text NOT NULL,
          description     text,
          is_system       boolean NOT NULL DEFAULT false,
          created_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE role_permissions (
          role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
          permission_id   uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
          PRIMARY KEY (role_id, permission_id)
        )
    """)

    op.execute("""
        CREATE TABLE user_roles (
          user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
          scope           jsonb NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY (user_id, role_id, scope)
        )
    """)

    # ============ DATA SETS ============
    op.execute("""
        CREATE TABLE data_sets (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          owner_dept_id   uuid REFERENCES departments(id) ON DELETE SET NULL,
          name            text NOT NULL,
          description     text,
          schema          jsonb NOT NULL,
          ui_config       jsonb NOT NULL DEFAULT '{}'::jsonb,
          indexes         jsonb NOT NULL DEFAULT '[]'::jsonb,
          workflow_id     uuid,
          ai_indexed      boolean NOT NULL DEFAULT true,
          sensitivity     text NOT NULL DEFAULT 'internal'
                          CHECK (sensitivity IN ('public','internal','confidential','restricted')),
          status          text NOT NULL DEFAULT 'active',
          created_by      uuid REFERENCES users(id) ON DELETE SET NULL,
          created_at      timestamptz NOT NULL DEFAULT now(),
          updated_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, name)
        )
    """)
    op.execute("CREATE INDEX ix_dataset_tenant ON data_sets(tenant_id)")

    # ============ DATA RECORDS ============
    op.execute("""
        CREATE TABLE data_records (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          dataset_id      uuid NOT NULL REFERENCES data_sets(id) ON DELETE CASCADE,
          department_id   uuid REFERENCES departments(id) ON DELETE SET NULL,
          payload         jsonb NOT NULL,
          status          text NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','soft_deleted')),
          version         integer NOT NULL DEFAULT 1,
          created_by      uuid REFERENCES users(id) ON DELETE SET NULL,
          updated_by      uuid REFERENCES users(id) ON DELETE SET NULL,
          created_at      timestamptz NOT NULL DEFAULT now(),
          updated_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX ix_records_dataset ON data_records(tenant_id, dataset_id) "
        "WHERE status='active'"
    )
    op.execute(
        "CREATE INDEX ix_records_dept ON data_records(tenant_id, department_id) "
        "WHERE status='active'"
    )

    # ============ RECORD VERSIONS (审批 + 历史) ============
    op.execute("""
        CREATE TABLE record_versions (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          record_id       uuid REFERENCES data_records(id) ON DELETE CASCADE,
          dataset_id      uuid NOT NULL REFERENCES data_sets(id) ON DELETE CASCADE,
          op              text NOT NULL CHECK (op IN ('insert','update','delete')),
          before_payload  jsonb,
          after_payload   jsonb,
          state           text NOT NULL DEFAULT 'pending'
                          CHECK (state IN ('pending','approved','rejected','applied','superseded','cancelled')),
          workflow_id     uuid,
          current_step    integer NOT NULL DEFAULT 0,
          proposed_by     uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          applied_at      timestamptz,
          reason          text,
          reject_reason   text,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX ix_rv_pending ON record_versions(tenant_id, state) "
        "WHERE state='pending'"
    )
    op.execute("CREATE INDEX ix_rv_record ON record_versions(record_id)")

    # ============ WORKFLOWS ============
    op.execute("""
        CREATE TABLE workflows (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          name            text NOT NULL,
          description     text,
          steps           jsonb NOT NULL,
          is_default      boolean NOT NULL DEFAULT false,
          created_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, name)
        )
    """)

    # Add FK from data_sets.workflow_id to workflows (deferred until workflows table exists)
    op.execute("""
        ALTER TABLE data_sets
          ADD CONSTRAINT fk_dataset_workflow
          FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE TABLE approval_actions (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          version_id      uuid NOT NULL REFERENCES record_versions(id) ON DELETE CASCADE,
          step_index      integer NOT NULL,
          approver_id     uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          decision        text NOT NULL CHECK (decision IN ('approve','reject')),
          comment         text,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_appr_version ON approval_actions(version_id)")

    # ============ AUDIT LOG ============
    op.execute("""
        CREATE TABLE audit_log (
          id              bigserial PRIMARY KEY,
          tenant_id       uuid REFERENCES tenants(id) ON DELETE SET NULL,
          user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
          action          text NOT NULL,
          resource_type   text NOT NULL,
          resource_id     text,
          detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
          ip              inet,
          user_agent      text,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_audit_tenant_time ON audit_log(tenant_id, created_at DESC)")

    # ============ AI CHUNKS (vector) ============
    op.execute("""
        CREATE TABLE chunks (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          dataset_id      uuid NOT NULL REFERENCES data_sets(id) ON DELETE CASCADE,
          record_id       uuid REFERENCES data_records(id) ON DELETE CASCADE,
          department_id   uuid REFERENCES departments(id) ON DELETE SET NULL,
          sensitivity     text NOT NULL DEFAULT 'internal',
          source_field    text,
          text            text NOT NULL,
          embedding       vector(1536),
          embedded_at     timestamptz NOT NULL DEFAULT now(),
          source_version  integer NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute(
        "CREATE INDEX ix_chunks_filter ON chunks(tenant_id, dataset_id, department_id, sensitivity)"
    )
    op.execute("CREATE INDEX ix_chunks_record ON chunks(record_id)")

    # ============ AI 会话 ============
    op.execute("""
        CREATE TABLE ai_conversations (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title           text,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE ai_messages (
          id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          conversation_id uuid NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          role            text NOT NULL CHECK (role IN ('user','assistant','system','tool')),
          content         text NOT NULL,
          citations       jsonb NOT NULL DEFAULT '[]'::jsonb,
          guardrail       jsonb,
          tokens_in       integer,
          tokens_out      integer,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_msg_conv ON ai_messages(conversation_id, created_at)")

    # ============ Sessions / Refresh Tokens ============
    op.execute("""
        CREATE TABLE refresh_tokens (
          jti             uuid PRIMARY KEY,
          tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at      timestamptz NOT NULL,
          revoked_at      timestamptz,
          user_agent      text,
          ip              inet,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_rt_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL")


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS ai_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS ai_conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS approval_actions CASCADE")
    op.execute("DROP TABLE IF EXISTS workflows CASCADE")
    op.execute("DROP TABLE IF EXISTS record_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS data_records CASCADE")
    op.execute("DROP TABLE IF EXISTS data_sets CASCADE")
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS role_permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS roles CASCADE")
    op.execute("DROP TABLE IF EXISTS permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_departments CASCADE")
    op.execute("DROP TABLE IF EXISTS departments CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")
    op.execute('DROP EXTENSION IF EXISTS "citext"')
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
