"""Authentication tests - Part 1: Login tests.

Tests:
- Login success
- Login failure (wrong password, wrong email, wrong tenant)
- Login with inactive user
- Admin login
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User
from app.utils.hashing import hash_password


@pytest.fixture
async def test_tenant(db: AsyncSession) -> Tenant:
    """Create test tenant."""
    tenant = Tenant(
        slug="test-auth",
        name="Test Auth Tenant",
        status="active",
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.fixture
async def test_user(db: AsyncSession, test_tenant: Tenant) -> User:
    """Create test user with password 'testpass123'."""
    user = User(
        tenant_id=test_tenant.id,
        email="testuser@test.com",
        display_name="Test User",
        password_hash=hash_password("testpass123"),
        status="active",
        is_tenant_admin=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def test_admin(db: AsyncSession, test_tenant: Tenant) -> User:
    """Create test admin user."""
    admin = User(
        tenant_id=test_tenant.id,
        email="admin@test.com",
        display_name="Admin User",
        password_hash=hash_password("adminpass123"),
        status="active",
        is_tenant_admin=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


class TestLogin:
    """Test login endpoint."""

    async def test_login_success(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test successful login returns tokens and user info."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900  # 15 minutes
        
        # Check user info
        assert data["user"]["email"] == "testuser@test.com"
        assert data["user"]["display_name"] == "Test User"
        assert data["user"]["is_tenant_admin"] is False
        assert data["user"]["tenant_slug"] == "test-auth"

    async def test_login_wrong_password(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test login with wrong password returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "wrongpassword",
            },
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"

    async def test_login_wrong_email(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
    ) -> None:
        """Test login with non-existent email returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "nonexistent@test.com",
                "password": "testpass123",
            },
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"

    async def test_login_wrong_tenant(
        self,
        client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test login with wrong tenant slug returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "nonexistent-tenant",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"

    async def test_login_inactive_user(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test login with inactive user returns 401."""
        # Deactivate user
        test_user.status = "inactive"
        await db.commit()
        
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        
        assert response.status_code == 401

    async def test_login_admin(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_admin: User,
    ) -> None:
        """Test admin login returns is_tenant_admin=true."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "admin@test.com",
                "password": "adminpass123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_tenant_admin"] is True


class TestTokenValidation:
    """Test token validation and authorization."""

    async def test_get_me_success(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test /auth/me with valid token returns user info."""
        # Login first
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        access_token = login_response.json()["access_token"]
        
        # Get user info
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@test.com"
        assert data["status"] == "active"

    async def test_get_me_no_token(self, client: AsyncClient) -> None:
        """Test /auth/me without token returns 401."""
        response = await client.get("/api/v1/auth/me")
        
        assert response.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient) -> None:
        """Test /auth/me with invalid token returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        assert response.status_code == 401


class TestPasswordChange:
    """Test password change functionality."""

    async def test_change_password_success(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test successful password change."""
        # Login first
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        access_token = login_response.json()["access_token"]
        
        # Change password
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "testpass123",
                "new_password": "newpass12345",
            },
        )
        
        assert response.status_code == 204
        
        # Verify can login with new password
        new_login = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "newpass12345",
            },
        )
        assert new_login.status_code == 200

    async def test_change_password_wrong_old_password(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test password change with wrong old password fails."""
        # Login first
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        access_token = login_response.json()["access_token"]
        
        # Try to change password with wrong old password
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "wrongpassword",
                "new_password": "newpass12345",
            },
        )
        
        assert response.status_code == 401

    async def test_change_password_too_short(
        self,
        client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ) -> None:
        """Test password change with too short password fails."""
        # Login first
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "test-auth",
                "email": "testuser@test.com",
                "password": "testpass123",
            },
        )
        access_token = login_response.json()["access_token"]
        
        # Try to change password to short password
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "testpass123",
                "new_password": "short",
            },
        )
        
        assert response.status_code == 422
