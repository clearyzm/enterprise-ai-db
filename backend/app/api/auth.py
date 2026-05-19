"""Authentication API endpoints.

Routes:
- POST /auth/login - User login
- POST /auth/refresh - Refresh access token (Phase 3+)
- POST /auth/logout - Logout and revoke tokens (Phase 3+)
- GET /auth/me - Get current user info
- POST /auth/change-password - Change password
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Request/Response Models
# ============================================================================


class LoginRequest(BaseModel):
    """Login request body."""

    tenant_slug: str = Field(..., min_length=1, max_length=100, description="Tenant slug (e.g., 'demo')")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")


class LoginResponse(BaseModel):
    """Login response with tokens and user info."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Opaque refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    user: dict = Field(..., description="User information")


class ChangePasswordRequest(BaseModel):
    """Change password request body."""

    old_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=10, description="New password (min 10 characters)")


class UserInfoResponse(BaseModel):
    """Current user information response."""

    id: str
    email: str
    display_name: str
    status: str
    is_tenant_admin: bool
    tenant_id: str
    tenant_slug: str
    tenant_name: str
    roles: list[dict]
    departments: list[dict]
    last_login_at: str | None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """User login with email and password.
    
    Returns access token (JWT, 15min TTL) and refresh token (opaque, 30d TTL).
    
    **Request:**
    ```json
    {
        "tenant_slug": "demo",
        "email": "admin@demo.com",
        "password": "demo123456"
    }
    ```
    
    **Response:**
    ```json
    {
        "access_token": "eyJ...",
        "refresh_token": "abc123...",
        "token_type": "bearer",
        "expires_in": 900,
        "user": {
            "id": "...",
            "email": "admin@demo.com",
            "display_name": "Admin User",
            "is_tenant_admin": true,
            "tenant_id": "...",
            "tenant_slug": "demo"
        }
    }
    ```
    
    **Errors:**
    - 401: Invalid credentials (tenant, email, or password)
    """
    service = AuthService(db)
    result = await service.login(
        tenant_slug=request.tenant_slug,
        email=request.email,
        password=request.password,
    )
    return LoginResponse(**result)


@router.get("/me", response_model=UserInfoResponse)
async def get_me(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserInfoResponse:
    """Get current authenticated user information.
    
    Returns user profile with roles, departments, and permissions summary.
    
    **Headers:**
    ```
    Authorization: Bearer <access_token>
    ```
    
    **Response:**
    ```json
    {
        "id": "...",
        "email": "admin@demo.com",
        "display_name": "Admin User",
        "status": "active",
        "is_tenant_admin": true,
        "tenant_id": "...",
        "tenant_slug": "demo",
        "tenant_name": "Demo Corporation",
        "roles": [
            {
                "role_id": "...",
                "role_name": "tenant_admin",
                "scope": {}
            }
        ],
        "departments": [
            {
                "department_id": "...",
                "department_name": "Sales",
                "is_primary": true
            }
        ],
        "last_login_at": "2026-05-12T10:30:00Z"
    }
    ```
    
    **Errors:**
    - 401: Invalid or expired token
    """
    service = AuthService(db)
    result = await service.get_current_user_info(user.id)
    return UserInfoResponse(**result)


@router.post("/change-password", status_code=204)
async def change_password(
    request: ChangePasswordRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Change current user's password.
    
    Requires current password for verification.
    
    **Headers:**
    ```
    Authorization: Bearer <access_token>
    ```
    
    **Request:**
    ```json
    {
        "old_password": "demo123456",
        "new_password": "newSecurePass123"
    }
    ```
    
    **Response:** 204 No Content
    
    **Errors:**
    - 401: Invalid or expired token, or old password incorrect
    - 422: New password doesn't meet requirements (min 10 characters)
    """
    service = AuthService(db)
    await service.change_password(
        user_id=user.id,
        old_password=request.old_password,
        new_password=request.new_password,
    )


# ============================================================================
# Phase 3+ Endpoints (Placeholder)
# ============================================================================


@router.post("/refresh")
async def refresh_token() -> dict:
    """Refresh access token using refresh token.
    
    **Phase 3+ Implementation:**
    - Validate refresh token from database
    - Check expiration and revocation status
    - Generate new access token
    - Rotate refresh token (single-use)
    - Return new tokens
    
    **Not implemented in Phase 2** (refresh tokens are stateless).
    """
    return {
        "error": "not_implemented",
        "message": "Token refresh will be implemented in Phase 3+",
    }


@router.post("/logout")
async def logout() -> dict:
    """Logout and revoke tokens.
    
    **Phase 3+ Implementation:**
    - Revoke refresh token in database
    - Add access token JTI to Redis blacklist (until expiration)
    - Clear client-side tokens
    
    **Not implemented in Phase 2** (tokens are stateless).
    """
    return {
        "error": "not_implemented",
        "message": "Logout will be implemented in Phase 3+",
    }
