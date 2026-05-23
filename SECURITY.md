# Security Model

## Threat Model

This is a multi-tenant SaaS data platform. The threat model includes:

| Threat | Mitigation |
|---|---|
| Cross-tenant data leak | PostgreSQL Row-Level Security + application WHERE filter (double layer) |
| Privilege escalation (越权访问) | RBAC at API endpoint level + scope filter at service level |
| Approver self-approval (自审) | Workflow engine rejects when `submitter_id == approver_id` |
| AI exfiltration of out-of-scope data | PermissionService.compute_ai_access strictly filters dataset_ids before vector retrieval |
| Audit log tampering | append-only `audit_log` table; no UPDATE/DELETE endpoints exposed |

## Three Layers of Tenant Isolation

```
┌─ Application layer ─────────────────────────────┐
│   Every query has `WHERE tenant_id = ?`         │
│   Code review enforced via lint rules            │
└─────────────────────────────────────────────────┘
                ↓ defense in depth
┌─ Middleware layer ──────────────────────────────┐
│   get_db dependency extracts tenant_id from JWT │
│   and SET LOCAL app.tenant_id = '<uuid>'         │
└─────────────────────────────────────────────────┘
                ↓ defense in depth
┌─ Database layer ────────────────────────────────┐
│   PostgreSQL RLS policy `tenant_isolation` on  │
│   5 core tables. FORCE ROW LEVEL SECURITY ON.   │
└─────────────────────────────────────────────────┘
```

A query that bypasses all three layers is required to leak data.

## Tables with RLS Enabled

| Table | Policy |
|---|---|
| `users` | `tenant_id::text = current_setting('app.tenant_id')` |
| `departments` | same |
| `data_sets` | same |
| `data_records` | same |
| `record_versions` | same |

Other tables (`tenants`, `audit_log`) intentionally exclude RLS:
- `tenants`: chicken-and-egg with login (login must query tenants table before tenant_id is known)
- `audit_log`: allows `tenant_id = NULL` rows for system events (e.g. login attempts before tenant is resolved)

## RBAC Permission Boundary

| Role | Permissions |
|---|---|
| `tenant_admin` | All permissions; bypass approvals (fast-path) |
| `approver` | `approve:record`, `reject:record`, `read:record` |
| `editor` | `read:record`, `write:record` |
| `viewer` | `read:record` only |
| `ai_user` | `ai_query:dataset` |

A user with `editor` role calling `POST /approvals/<id>/approve` is rejected with **403 Forbidden** at the `require_perm("approve", "record")` dependency, **before** reaching the business logic.

## AI Permission-Aware Retrieval

`PermissionService.compute_ai_access(user)` returns an `AIAccessBundle`:

```python
class AIAccessBundle:
    dataset_ids: list[UUID]           # empty = all (admin), non-empty = whitelist
    dept_ids: list[UUID]              # department scope
    allowed_sensitivities: list[str]  # ["public", "internal", "confidential", "restricted"]
```

The LangGraph RAG pipeline reads this bundle **before** vector retrieval and filters the search index. The LLM never sees data outside the user's scope.

## Production Deployment Notes

⚠️ **Critical**: PostgreSQL `superuser` and any role with `BYPASSRLS` ignore Row-Level Security policies. Production deployments **must** connect with a non-superuser role:

```sql
-- Example production setup
CREATE ROLE app_user LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
```

The `DATABASE_URL` should use `app_user`, not `postgres`. RLS testing in this repo creates a `rls_test_role` to faithfully simulate this constraint.

## Validation: Security Contract Tests

Run the contract suite:

```bash
docker compose --profile test up -d postgres-test
docker compose exec backend uv run pytest tests/test_security_contracts.py -v
```

Tests cover:

- **A. Cross-tenant isolation (3 tests)**:
  - Tenant A's query cannot see Tenant B's dataset (RLS blocks at DB layer)
  - Tenant B can see own dataset (positive control)
  - No tenant context → 0 rows (fail-closed)

- **B. RBAC permission boundary (1 test)**:
  - Editor (no approve permission) gets 403 on approval endpoint
  - Approver (has permission) passes through to 404 (record not found) — proves RBAC fires before business logic

- **C. AI scope guardrail (2 tests)**:
  - Sales user's `compute_ai_access` excludes finance dataset
  - Admin's `compute_ai_access` returns unrestricted (empty whitelist)

## Discovered & Fixed Issues

During pytest integration test development, two production-grade security defects were discovered:

### Defect 1: RLS migration was an empty shell

- `migrations/versions/0002_rls.py` had an empty `upgrade()` body
- All `pg_tables.rowsecurity` were `false`
- Multi-tenant isolation depended solely on application-layer WHERE filters
- **Fix**: New migration `0010_enable_row_level_security.py`

### Defect 2: Middleware ↔ Session disconnect

- `TenantContextMiddleware` set `app.tenant_id` on its own session (`request.state.db`)
- Route handlers used `Depends(get_db)` which created a separate session, never receiving the tenant context
- Even with RLS enabled, queries would not filter correctly
- **Fix**: `get_db` now extracts tenant_id from JWT and applies `SET LOCAL` independently, decoupled from middleware

Both issues are documented in commit history; the fixes are validated by the security contract tests above.
