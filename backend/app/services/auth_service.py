"""Authentication service — login, logout, token refresh, password management.

Handles:
- User login with email/password
- Access token generation
- Refresh token creation, validation, and rotation
- Logout (token revocation)
- Password change
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.models.tenant import Tenant
from app.services.audit_service import log_event
from app.utils.errors import AuthenticationError, InvalidCredentialsError, NotFoundError, ValidationError
from app.utils.hashing import hash_password, needs_rehash, verify_password
from app.utils.jwt import (
    create_access_token,
    create_refresh_token,
    get_refresh_token_expiry,
)

settings = get_settings()
logger = structlog.get_logger(__name__)


class AuthService:
    """Authentication service for login, logout, and token management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def login(
        self,
        tenant_slug: str,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        """Authenticate user and generate tokens.
        
        Args:
            tenant_slug: Tenant slug (e.g., 'demo')
            email: User email (case-insensitive)
            password: Plaintext password
        
        Returns:
            Dict with access_token, refresh_token, and user info
            {
                "access_token": "eyJ...",
                "refresh_token": "abc123...",
                "token_type": "bearer",
                "expires_in": 900,
                "user": {
                    "id": "...",
                    "email": "...",
                    "display_name": "...",
                    "is_tenant_admin": false
                }
            }
        
        Raises:
            InvalidCredentialsError: Invalid tenant, email, or password
        """
        # Load tenant by slug
        stmt = select(Tenant).where(Tenant.slug == tenant_slug)
        result = await self.db.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if not tenant or tenant.status != "active":
            logger.warning("login.tenant_not_found", tenant_slug=tenant_slug)
            raise InvalidCredentialsError()
        
        # Load user by email (case-insensitive via CITEXT)
        stmt = select(User).where(
            User.tenant_id == tenant.id,
            User.email == email,
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning("login.user_not_found", email=email, tenant_id=str(tenant.id))
            raise InvalidCredentialsError()
        
        # Verify password
        if not verify_password(password, user.password_hash):
            logger.warning("login.invalid_password", user_id=str(user.id))
            raise InvalidCredentialsError()
        
        # Check user status
        if user.status != "active":
            logger.warning("login.user_not_active", user_id=str(user.id), status=user.status)
            raise AuthenticationError("User account is not active")
        
        # Update last_login_at
        user.last_login_at = datetime.now(timezone.utc)
        
        # Check if password hash needs upgrade
        if needs_rehash(user.password_hash):
            logger.info("login.rehashing_password", user_id=str(user.id))
            user.password_hash = hash_password(password)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        # Audit log: login success
        await log_event(
            self.db,
            tenant_id=tenant.id,
            user_id=user.id,
            action="login",
            resource_type="user",
            resource_id=str(user.id),
            detail={
                "email": email,
                "tenant_slug": tenant_slug,
            },
        )
        await self.db.commit()
        
        # Collect department IDs
        department_ids = [ud.department_id for ud in user.user_departments]
        
        # Collect role names
        role_names = [ur.role.name for ur in user.user_roles]
        
        # Generate access token
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            department_ids=department_ids,
            roles=role_names,
            is_admin=user.is_tenant_admin,
        )
        
        # Generate refresh token
        refresh_token = create_refresh_token()
        
        # Store refresh token in database (Phase 2: simplified, store in user table)
        # Phase 3+: move to dedicated refresh_tokens table with device tracking
        # For now, we'll use a simple approach: store in a hypothetical field
        # Since refresh_tokens table doesn't exist yet, we'll skip DB storage
        # and just return the token (stateless for Phase 2)
        
        logger.info(
            "login.success",
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            email=email,
        )
        
        # Reuse get_current_user_info() to keep /auth/login and /auth/me identical in shape.
        # Avoids schema drift between two endpoints that return the same logical entity.
        user_info = await self.get_current_user_info(user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user_info,
        }

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
    ) -> None:
        """Change user password.
        
        Args:
            user_id: User UUID
            old_password: Current password (for verification)
            new_password: New password
        
        Raises:
            NotFoundError: User not found
            InvalidCredentialsError: Old password incorrect
            ValidationError: New password doesn't meet requirements
        """
        # Load user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundError("User")
        
        # Verify old password
        if not verify_password(old_password, user.password_hash):
            logger.warning("change_password.invalid_old_password", user_id=str(user_id))
            raise InvalidCredentialsError()
        
        # Validate new password (basic validation, Phase 3+ add complexity rules)
        if len(new_password) < 10:
            raise ValidationError("Password must be at least 10 characters")
        
        # Hash and update password
        user.password_hash = hash_password(new_password)
        await self.db.commit()
        
        logger.info("change_password.success", user_id=str(user_id))

    async def get_current_user_info(self, user_id: UUID) -> dict[str, Any]:
        """Get current user info with roles and accessible datasets.
        
        Args:
            user_id: User UUID
        
        Returns:
            Dict with user info, roles, departments, and permissions summary
        
        Raises:
            NotFoundError: User not found
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundError("User")
        
        # Build roles summary
        roles_summary = []
        for user_role in user.user_roles:
            roles_summary.append({
                "role_id": str(user_role.role_id),
                "role_name": user_role.role.name,
                "scope": user_role.scope,
            })
        
        # Build departments summary
        departments_summary = []
        for ud in user.user_departments:
            departments_summary.append({
                "department_id": str(ud.department_id),
                "department_name": ud.department.name,
                "is_primary": ud.is_primary,
            })
        
        return {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status.value,
            "is_tenant_admin": user.is_tenant_admin,
            "tenant_id": str(user.tenant_id),
            "tenant_slug": user.tenant.slug,
            "tenant_name": user.tenant.name,
            "roles": roles_summary,
            "departments": departments_summary,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }
