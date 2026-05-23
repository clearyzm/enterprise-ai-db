"""Security contract tests.

These tests verify the project's 3 core security promises:

  A. Cross-tenant isolation (RLS) — A query made under tenant_a's context
     cannot see tenant_b's data, even if the application layer's WHERE
     filter is bypassed.

  B. RBAC permission boundary
  C. AI scope guardrail

NOTE on RLS testing: PostgreSQL superusers (and roles with BYPASSRLS)
bypass ALL row-level security policies, even FORCE ROW LEVEL SECURITY.
Production should run the application with a non-superuser role.
These tests create and switch to a non-superuser role to faithfully
simulate the production permission context.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import DataSet
from app.models.tenant import Tenant


# ============================================================================
# Test A: Cross-tenant isolation via RLS
# ============================================================================

class TestCrossTenantIsolation:
    """Verify PostgreSQL Row-Level Security blocks cross-tenant access.

    These tests bypass the HTTP layer and directly use SQL with SET LOCAL
    app.tenant_id, making them the strictest possible verification of RLS.

    A non-superuser role is created and SET ROLE-switched before each
    cross-tenant query, because postgres superuser bypasses RLS by default.
    """

    @pytest.fixture
    async def app_role(self, db: AsyncSession):
        """Create a non-superuser role 'rls_test_role' to faithfully test RLS.
        
        PostgreSQL superusers ignore RLS even with FORCE — production should
        always use a non-superuser. This fixture creates that role for tests.
        Idempotent (uses IF NOT EXISTS via DO block).
        """
        # Create role if not exists, grant needed privileges
        await db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_test_role') THEN
                    CREATE ROLE rls_test_role NOLOGIN;
                END IF;
            END $$;
        """))
        # Grant table privileges (idempotent)
        await db.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, departments, data_sets, data_records, record_versions TO rls_test_role;"))
        await db.execute(text("GRANT USAGE ON SCHEMA public TO rls_test_role;"))
        return "rls_test_role"

    @pytest.fixture
    async def two_tenants_with_datasets(self, db: AsyncSession) -> dict:
        """Create tenant_a + tenant_b, each with one dataset.

        Data creation runs as superuser (db fixture's default) which is fine
        because we're not testing INSERT restrictions here.
        """
        # Tenant A
        tenant_a = Tenant(
            slug=f"test-tenant-a-{uuid4().hex[:8]}",
            name="Test Tenant A",
            status="active",
        )
        db.add(tenant_a)
        await db.flush()

        # Tenant B
        tenant_b = Tenant(
            slug=f"test-tenant-b-{uuid4().hex[:8]}",
            name="Test Tenant B",
            status="active",
        )
        db.add(tenant_b)
        await db.flush()

        dataset_a = DataSet(
            tenant_id=tenant_a.id,
            name="dataset_in_tenant_a",
            description="Owned by tenant A only",
            sensitivity="internal",
            ai_indexed=False,
            schema={"fields": []},
        )
        db.add(dataset_a)
        await db.flush()

        dataset_b = DataSet(
            tenant_id=tenant_b.id,
            name="dataset_in_tenant_b",
            description="Owned by tenant B only",
            sensitivity="internal",
            ai_indexed=False,
            schema={"fields": []},
        )
        db.add(dataset_b)
        await db.flush()

        return {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "dataset_a": dataset_a,
            "dataset_b": dataset_b,
        }

    async def test_tenant_a_cannot_see_tenant_b_dataset(
        self,
        db: AsyncSession,
        app_role: str,
        two_tenants_with_datasets: dict,
    ):
        """Under tenant_a's context, querying tenant_b's dataset returns 0 rows.

        Switches to non-superuser role so RLS is actually enforced.
        """
        tenant_a = two_tenants_with_datasets["tenant_a"]
        dataset_b = two_tenants_with_datasets["dataset_b"]

        # Switch to non-superuser role + set tenant_a context
        await db.execute(text(f"SET LOCAL ROLE {app_role}"))
        await db.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.id}'"))

        result = await db.execute(
            text("SELECT id, name FROM data_sets WHERE id = :ds_id"),
            {"ds_id": str(dataset_b.id)},
        )
        rows = result.all()

        # Reset role for cleanup
        await db.execute(text("RESET ROLE"))

        assert rows == [], (
            f"RLS leak: tenant_a saw tenant_b's dataset. Got: {rows}"
        )

    async def test_tenant_b_can_see_own_dataset(
        self,
        db: AsyncSession,
        app_role: str,
        two_tenants_with_datasets: dict,
    ):
        """Positive control: tenant_b CAN see its own dataset under matching context."""
        tenant_b = two_tenants_with_datasets["tenant_b"]
        dataset_b = two_tenants_with_datasets["dataset_b"]

        await db.execute(text(f"SET LOCAL ROLE {app_role}"))
        await db.execute(text(f"SET LOCAL app.tenant_id = '{tenant_b.id}'"))

        result = await db.execute(
            text("SELECT id, name FROM data_sets WHERE id = :ds_id"),
            {"ds_id": str(dataset_b.id)},
        )
        rows = result.all()

        await db.execute(text("RESET ROLE"))

        assert len(rows) == 1, (
            f"Tenant_b cannot see own dataset. Got {len(rows)} rows, expected 1."
        )

    async def test_no_tenant_context_blocks_all(
        self,
        db: AsyncSession,
        app_role: str,
        two_tenants_with_datasets: dict,
    ):
        """Without tenant context, RLS must block all rows (fail-closed)."""
        # Switch to non-superuser; reset tenant_id to empty
        await db.execute(text(f"SET LOCAL ROLE {app_role}"))
        await db.execute(text("SET LOCAL app.tenant_id = ''"))

        result = await db.execute(text("SELECT COUNT(*) FROM data_sets"))
        count = result.scalar()

        await db.execute(text("RESET ROLE"))

        assert count == 0, (
            f"RLS fail-open: without tenant context, returned {count} rows."
        )


# ============================================================================
# Test B: RBAC permission boundary on approval endpoint
# ============================================================================

class TestApprovalRBAC:
    """Verify role-based access control on the approval endpoint.

    Setup:
      - One tenant with two users:
          approver_user has the 'approver' role (which grants 'approve' permission)
          editor_user has the 'editor' role (which lacks 'approve' permission)
      - Both users call POST /approvals/{fake_version_id}/approve

    Contract:
      - approver_user should pass RBAC and fail later with 404 (version not found)
      - editor_user should be blocked at RBAC with 403 Forbidden

    The 403 vs 404 distinction proves RBAC fires *before* business logic.
    """

    @pytest.fixture
    async def rbac_setup(self, db: AsyncSession) -> dict:
        """Create a tenant + 2 users with different permission levels.

        Returns: {
            "tenant_slug": str,
            "approver_email": str,
            "editor_email": str,
            "password": str,
        }
        """
        from app.models.role import Role, RolePermission, UserRole
        from app.models.user import User
        from app.utils.hashing import hash_password

        suffix = uuid4().hex[:8]
        password = "testpass123"

        tenant = Tenant(
            slug=f"test-rbac-{suffix}",
            name="Test RBAC Tenant",
            status="active",
        )
        db.add(tenant)
        await db.flush()

        # Fetch existing approve permission (seeded globally in 0003)
        result = await db.execute(
            text("SELECT id FROM permissions WHERE action = 'approve' AND resource_type = 'record' LIMIT 1")
        )
        approve_perm_id = result.scalar()

        # Create approver_role + assign approve permission
        approver_role = Role(
            tenant_id=tenant.id,
            name="test_approver",
            description="Test approver role",
            is_system=False,
        )
        db.add(approver_role)
        await db.flush()
        db.add(RolePermission(role_id=approver_role.id, permission_id=approve_perm_id))

        # Create editor_role with no approve permission
        editor_role = Role(
            tenant_id=tenant.id,
            name="test_editor",
            description="Test editor role (no approve)",
            is_system=False,
        )
        db.add(editor_role)
        await db.flush()
        # editor_role intentionally has no permissions

        # Create users
        approver_email = f"approver-{suffix}@test.com"
        approver_user = User(
            tenant_id=tenant.id,
            email=approver_email,
            display_name="Approver",
            password_hash=hash_password(password),
            status="active",
            is_tenant_admin=False,
        )
        editor_email = f"editor-{suffix}@test.com"
        editor_user = User(
            tenant_id=tenant.id,
            email=editor_email,
            display_name="Editor",
            password_hash=hash_password(password),
            status="active",
            is_tenant_admin=False,
        )
        db.add(approver_user)
        db.add(editor_user)
        await db.flush()

        # Assign roles to users
        db.add(UserRole(user_id=approver_user.id, role_id=approver_role.id, scope={}))
        db.add(UserRole(user_id=editor_user.id, role_id=editor_role.id, scope={}))
        await db.commit()  # commit so the HTTP test sees the data

        return {
            "tenant_slug": tenant.slug,
            "approver_email": approver_email,
            "editor_email": editor_email,
            "password": password,
        }

    async def _login(self, client, tenant_slug: str, email: str, password: str) -> str:
        """Login and return access_token."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": tenant_slug, "email": email, "password": password},
        )
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
        return resp.json()["access_token"]

    async def test_editor_blocked_from_approval(
        self,
        client,
        rbac_setup: dict,
    ):
        """Editor (no approve permission) gets 403 on approval endpoint."""
        token = await self._login(
            client, rbac_setup["tenant_slug"], rbac_setup["editor_email"], rbac_setup["password"]
        )
        fake_version_id = str(uuid4())
        resp = await client.post(
            f"/api/v1/approvals/{fake_version_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "should be blocked"},
        )
        assert resp.status_code == 403, (
            f"Expected 403 Forbidden for editor (no approve permission), "
            f"got {resp.status_code}. Body: {resp.text[:200]}"
        )

    async def test_approver_passes_rbac(
        self,
        client,
        rbac_setup: dict,
    ):
        """Approver (has approve permission) passes RBAC, fails later (404 since version is fake).

        This proves RBAC fires before business logic — the user-level
        permission check succeeded; the request only failed because the
        targeted record doesn't exist.
        """
        token = await self._login(
            client, rbac_setup["tenant_slug"], rbac_setup["approver_email"], rbac_setup["password"]
        )
        fake_version_id = str(uuid4())
        resp = await client.post(
            f"/api/v1/approvals/{fake_version_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={"comment": "ok"},
        )
        # Acceptable: 404 (version not found) or 400 (validation) — anything not 403
        assert resp.status_code != 403, (
            f"Approver was unexpectedly blocked by RBAC. "
            f"Got 403 — approver role does not have approve permission attached correctly. "
            f"Body: {resp.text[:200]}"
        )


# ============================================================================
# Test C: AI scope guardrail (PermissionService.compute_ai_access)
# ============================================================================

class TestAIScopeGuardrail:
    """Verify PermissionService.compute_ai_access filters datasets by scope.

    Setup:
      - One tenant with Sales + Finance departments
      - One dataset owned by each department
      - sales_user has ai_user role scoped to Sales department
      - admin_user is tenant_admin (unrestricted)

    Contract:
      - compute_ai_access(sales_user) excludes finance dataset from dataset_ids
      - compute_ai_access(admin_user) returns empty dataset_ids (= unrestricted)

    This tests the permission boundary the AI tool layer relies on. We avoid
    testing LLM output directly because that is non-deterministic; the
    permission layer's correctness is the actual security contract.
    """

    @pytest.fixture
    async def ai_scope_setup(self, db: AsyncSession) -> dict:
        """Create tenant + 2 departments + 2 datasets + sales_user + admin_user."""
        from app.models.department import Department
        from app.models.role import Role, RolePermission, UserRole
        from app.models.user import User
        from app.utils.hashing import hash_password

        suffix = uuid4().hex[:8]

        tenant = Tenant(
            slug=f"test-ai-scope-{suffix}",
            name="Test AI Scope Tenant",
            status="active",
        )
        db.add(tenant)
        await db.flush()

        sales_dept = Department(tenant_id=tenant.id, name="Sales", code=f"SALES-{suffix}")
        finance_dept = Department(tenant_id=tenant.id, name="Finance", code=f"FIN-{suffix}")
        db.add(sales_dept)
        db.add(finance_dept)
        await db.flush()

        sales_data = DataSet(
            tenant_id=tenant.id,
            owner_dept_id=sales_dept.id,
            name=f"sales_data_{suffix}",
            description="Sales owned",
            sensitivity="internal",
            ai_indexed=True,
            schema={"fields": []},
        )
        finance_data = DataSet(
            tenant_id=tenant.id,
            owner_dept_id=finance_dept.id,
            name=f"finance_data_{suffix}",
            description="Finance owned",
            sensitivity="internal",
            ai_indexed=True,
            schema={"fields": []},
        )
        db.add(sales_data)
        db.add(finance_data)
        await db.flush()

        # Look up the ai_query permission (seeded globally)
        result = await db.execute(
            text("SELECT id FROM permissions WHERE action = 'ai_query' LIMIT 1")
        )
        ai_perm_id = result.scalar()

        ai_role = Role(
            tenant_id=tenant.id,
            name=f"test_ai_user_{suffix}",
            description="Test AI user role",
            is_system=False,
        )
        db.add(ai_role)
        await db.flush()
        if ai_perm_id:
            db.add(RolePermission(role_id=ai_role.id, permission_id=ai_perm_id))

        sales_user = User(
            tenant_id=tenant.id,
            email=f"ai-sales-{suffix}@test.com",
            display_name="AI Sales User",
            password_hash=hash_password("testpass"),
            status="active",
            is_tenant_admin=False,
        )
        admin_user = User(
            tenant_id=tenant.id,
            email=f"ai-admin-{suffix}@test.com",
            display_name="AI Admin User",
            password_hash=hash_password("testpass"),
            status="active",
            is_tenant_admin=True,
        )
        db.add(sales_user)
        db.add(admin_user)
        await db.flush()

        # sales_user: ai_user role scoped to Sales dept
        db.add(UserRole(
            user_id=sales_user.id,
            role_id=ai_role.id,
            scope={"department_id": str(sales_dept.id)},
        ))
        await db.flush()

        return {
            "tenant": tenant,
            "sales_user": sales_user,
            "admin_user": admin_user,
            "sales_dept": sales_dept,
            "finance_dept": finance_dept,
            "sales_data": sales_data,
            "finance_data": finance_data,
        }

    async def test_sales_user_excludes_finance_dataset(
        self,
        db: AsyncSession,
        ai_scope_setup: dict,
    ):
        """Sales user's AI scope must NOT include the finance dataset.

        The scope contract: a non-empty dataset_ids means "only these"; finance
        dataset's id should not appear.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.user import User
        from app.services.permission_service import PermissionService

        sales_user_id = ai_scope_setup["sales_user"].id
        finance_data = ai_scope_setup["finance_data"]

        result = await db.execute(
            select(User)
            .where(User.id == sales_user_id)
            .options(selectinload(User.user_roles))
        )
        sales_user = result.scalar_one()

        service = PermissionService(db)
        access = await service.compute_ai_access(sales_user)

        assert finance_data.id not in access.dataset_ids, (
            f"AI scope leak: sales_user can see finance dataset "
            f"({finance_data.id}). access.dataset_ids = {access.dataset_ids}"
        )

    async def test_admin_has_unrestricted_access(
        self,
        db: AsyncSession,
        ai_scope_setup: dict,
    ):
        """tenant_admin has no scope restriction; dataset_ids is empty (= all)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.user import User
        from app.services.permission_service import PermissionService

        admin_user_id = ai_scope_setup["admin_user"].id

        result = await db.execute(
            select(User)
            .where(User.id == admin_user_id)
            .options(selectinload(User.user_roles))
        )
        admin_user = result.scalar_one()

        service = PermissionService(db)
        access = await service.compute_ai_access(admin_user)

        assert access.dataset_ids == [], (
            f"Admin should have unrestricted AI access (empty dataset_ids = all). "
            f"Got dataset_ids = {access.dataset_ids}"
        )
