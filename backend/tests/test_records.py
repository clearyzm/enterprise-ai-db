"""Record service tests.

Tests:
- Optimistic locking conflict returns 409 VERSION_CONFLICT
- Filter with illegal fields returns 400
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User
from app.models.department import Department
from app.models.dataset import DataSet
from app.models.record import DataRecord, RecordStatus
from app.utils.hashing import hash_password


@pytest.fixture
async def setup_record_test(db: AsyncSession) -> dict:
    """Setup tenant, user, department, dataset, and record."""
    tenant = Tenant(slug="test-rec", name="Test Records", status="active")
    db.add(tenant)
    await db.flush()
    
    dept = Department(tenant_id=tenant.id, name="Sales", status="active")
    db.add(dept)
    await db.flush()
    
    user = User(
        tenant_id=tenant.id,
        email="user@test.com",
        display_name="User",
        password_hash=hash_password("pass123456"),
        status="active",
        is_tenant_admin=True,
    )
    db.add(user)
    await db.flush()
    
    dataset = DataSet(
        tenant_id=tenant.id,
        name="Test Dataset",
        description="Test",
        owner_dept_id=dept.id,
        schema_def={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "amount": {"type": "number"},
            },
        },
        status="active",
    )
    db.add(dataset)
    await db.flush()
    
    record = DataRecord(
        tenant_id=tenant.id,
        dataset_id=dataset.id,
        data={"name": "Test", "amount": 100},
        status=RecordStatus.APPLIED,
        version=1,
    )
    db.add(record)
    await db.commit()
    
    return {
        "tenant": tenant,
        "user": user,
        "dataset": dataset,
        "record": record,
    }


class TestOptimisticLocking:
    """Test optimistic locking for concurrent updates."""

    async def test_version_conflict_returns_409(
        self,
        client: AsyncClient,
        db: AsyncSession,
        setup_record_test: dict,
    ) -> None:
        """Test concurrent update with stale version returns 409."""
        tenant = setup_record_test["tenant"]
        user = setup_record_test["user"]
        dataset = setup_record_test["dataset"]
        record = setup_record_test["record"]
        
        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": tenant.slug,
                "email": user.email,
                "password": "pass123456",
            },
        )
        token = login_resp.json()["access_token"]
        
        # First update (version 1 -> 2)
        update1 = await client.put(
            f"/api/v1/datasets/{dataset.id}/records/{record.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "data": {"name": "Updated 1", "amount": 200},
                "version": 1,
            },
        )
        assert update1.status_code in [200, 201, 204]
        
        # Second update with stale version (should fail)
        update2 = await client.put(
            f"/api/v1/datasets/{dataset.id}/records/{record.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "data": {"name": "Updated 2", "amount": 300},
                "version": 1,  # Stale version
            },
        )
        
        # Should return 409 VERSION_CONFLICT
        assert update2.status_code == 409
        data = update2.json()
        assert data["error_code"] == "VERSION_CONFLICT"


class TestFilterValidation:
    """Test filter validation for illegal fields."""

    async def test_filter_illegal_field_returns_400(
        self,
        client: AsyncClient,
        db: AsyncSession,
        setup_record_test: dict,
    ) -> None:
        """Test filter with non-existent field returns 400."""
        tenant = setup_record_test["tenant"]
        user = setup_record_test["user"]
        dataset = setup_record_test["dataset"]
        
        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": tenant.slug,
                "email": user.email,
                "password": "pass123456",
            },
        )
        token = login_resp.json()["access_token"]
        
        # Query with illegal field
        response = await client.get(
            f"/api/v1/datasets/{dataset.id}/records",
            headers={"Authorization": f"Bearer {token}"},
            params={"filter": '{"nonexistent_field": {"$eq": "value"}}'},
        )
        
        # Should return 400 BAD_REQUEST
        assert response.status_code == 400
        data = response.json()
        assert "error_code" in data

    async def test_valid_filter_succeeds(
        self,
        client: AsyncClient,
        db: AsyncSession,
        setup_record_test: dict,
    ) -> None:
        """Test filter with valid field succeeds."""
        tenant = setup_record_test["tenant"]
        user = setup_record_test["user"]
        dataset = setup_record_test["dataset"]
        
        # Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": tenant.slug,
                "email": user.email,
                "password": "pass123456",
            },
        )
        token = login_resp.json()["access_token"]
        
        # Query with valid field
        response = await client.get(
            f"/api/v1/datasets/{dataset.id}/records",
            headers={"Authorization": f"Bearer {token}"},
            params={"filter": '{"name": {"$eq": "Test"}}'},
        )
        
        # Should succeed
        assert response.status_code == 200
