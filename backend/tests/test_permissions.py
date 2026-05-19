"""Permission service tests.

Tests:
- Scope AND relationship verification
- compute_ai_access returns correct fields
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User
from app.models.department import Department
from app.models.role import Role, Permission
from app.models.user_role import UserRole
from app.models.dataset import DataSet
from app.services.permission_service import PermissionService
from app.utils.hashing import hash_password


@pytest.fixture
async def test_tenant(db: AsyncSession) -> Tenant:
    """Create test tenant."""
    tenant = Tenant(slug="test-perm", name="Test Permissions", status="active")
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.fixture
async def test_dept(db: AsyncSession, test_tenant: Tenant) -> Department:
    """Create test department."""
    dept = Department(tenant_id=test_tenant.id, name="Sales", status="active")
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


@pytest.fixture
async def viewer_role(db: AsyncSession, test_tenant: Tenant) -> Role:
    """Create viewer role with read permission."""
    role = Role(tenant_id=test_tenant.id, name="viewer", description="Viewer role")
    db.add(role)
    await db.flush()
    
    perm = Permission(role_id=role.id, action="read", resource_type="dataset")
    db.add(perm)
    await db.commit()
    await db.refresh(role)
    return role


@pytest.fixture
async def test_dataset(db: AsyncSession, test_tenant: Tenant, test_dept: Department) -> DataSet:
    """Create test dataset."""
    dataset = DataSet(
        tenant_id=test_tenant.id,
        name="Sales Data",
        description="Test dataset",
        owner_dept_id=test_dept.id,
        schema_def={"type": "object", "properties": {}},
        status="active",
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


class TestScopeMatching:
    """Test scope AND relationship verification."""

    async def test_empty_scope_matches_all(
        self,
        db: AsyncSession,
        test_tenant: Tenant,
        viewer_role: Role,
        test_dataset: DataSet,
    ) -> None:
        """Test empty scope {} grants full tenant access."""
        user = User(
            tenant_id=test_tenant.id,
            email="user@test.com",
            display_name="User",
            password_hash=hash_password("pass123456"),
            status="active",
            is_tenant_admin=False,
        )
        db.add(user)
        await db.flush()
        
        user_role = UserRole(user_id=user.id, role_id=viewer_role.id, scope={})
        db.add(user_role)
        await db.commit()
        await db.refresh(user)
        
        service = PermissionService(db)
        has_perm = await service.check(user, "read", "dataset", test_dataset)
        
        assert has_perm is True

    async def test_dataset_scope_matches(
        self,
        db: AsyncSession,
        test_tenant: Tenant,
        viewer_role: Role,
        test_dataset: DataSet,
    ) -> None:
        """Test dataset_ids scope matches specific dataset."""
        user = User(
            tenant_id=test_tenant.id,
            email="user@test.com",
            display_name="User",
            password_hash=hash_password("pass123456"),
            status="active",
            is_tenant_admin=False,
        )
        db.add(user)
        await db.flush()
        
        user_role = UserRole(
            user_id=user.id,
            role_id=viewer_role.id,
            scope={"dataset_ids": [str(test_dataset.id)]},
        )
        db.add(user_role)
        await db.commit()
        await db.refresh(user)
        
        service = PermissionService(db)
        has_perm = await service.check(user, "read", "dataset", test_dataset)
        
        assert has_perm is True


class TestComputeAIAccess:
    """Test compute_ai_access returns correct fields."""

    async def test_tenant_admin_gets_all_access(
        self,
        db: AsyncSession,
        test_tenant: Tenant,
    ) -> None:
        """Test tenant admin gets unrestricted AI access."""
        admin = User(
            tenant_id=test_tenant.id,
            email="admin@test.com",
            display_name="Admin",
            password_hash=hash_password("pass123456"),
            status="active",
            is_tenant_admin=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        
        service = PermissionService(db)
        access = await service.compute_ai_access(admin)
        
        assert access.dataset_ids == []  # Empty = all datasets
        assert access.dept_ids == []  # Empty = all departments
        assert access.allowed_sensitivities == ["public", "internal", "confidential", "restricted"]

    async def test_scoped_user_gets_limited_datasets(
        self,
        db: AsyncSession,
        test_tenant: Tenant,
        viewer_role: Role,
        test_dataset: DataSet,
    ) -> None:
        """Test user with dataset scope gets limited dataset access."""
        user = User(
            tenant_id=test_tenant.id,
            email="user@test.com",
            display_name="User",
            password_hash=hash_password("pass123456"),
            status="active",
            is_tenant_admin=False,
        )
        db.add(user)
        await db.flush()
        
        user_role = UserRole(
            user_id=user.id,
            role_id=viewer_role.id,
            scope={"dataset_ids": [str(test_dataset.id)]},
        )
        db.add(user_role)
        await db.commit()
        await db.refresh(user)
        
        service = PermissionService(db)
        access = await service.compute_ai_access(user)
        
        assert test_dataset.id in access.dataset_ids
        assert len(access.dataset_ids) == 1
