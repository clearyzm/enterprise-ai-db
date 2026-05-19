"""JWT token generation and validation.

Access tokens:
- HS256/RS256 signed JWT
- TTL: 15 minutes (configurable)
- Claims: sub (user_id), tid (tenant_id), roles, is_admin, jti, exp, iat

Refresh tokens:
- Opaque 256-bit random token (not JWT)
- Stored in database with expiration
- Single-use with rotation on refresh
- TTL: 30 days (configurable)
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from app.config import get_settings
from app.utils.errors import TokenExpiredError, TokenInvalidError

settings = get_settings()


def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    department_ids: list[UUID],
    roles: list[str],
    is_admin: bool,
) -> str:
    """Create a JWT access token.
    
    Args:
        user_id: User UUID
        tenant_id: Tenant UUID
        department_ids: List of department UUIDs user belongs to
        roles: List of role names (e.g., ['editor', 'approver'])
        is_admin: Whether user is tenant admin (bypasses permission checks)
    
    Returns:
        Signed JWT string
    
    Claims structure:
        {
            "sub": "<user_id>",
            "tid": "<tenant_id>",
            "did": ["<dept_id>", ...],
            "roles": ["editor", "approver"],
            "is_admin": false,
            "jti": "<uuid>",  # JWT ID for blacklist
            "exp": 1234567890,
            "iat": 1234567890
        }
    """
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "did": [str(did) for did in department_ids],
        "roles": roles,
        "is_admin": is_admin,
        "jti": secrets.token_urlsafe(16),  # JWT ID for blacklist on logout
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    
    token = jwt.encode(
        claims,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.
    
    Args:
        token: JWT string
    
    Returns:
        Decoded claims dict
    
    Raises:
        TokenExpiredError: Token has expired
        TokenInvalidError: Token is invalid or malformed
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except JWTError:
        raise TokenInvalidError()


def create_refresh_token() -> str:
    """Create an opaque refresh token (256-bit random).
    
    Refresh tokens are NOT JWTs. They are stored in the database
    with expiration timestamp and user association.
    
    Returns:
        URL-safe random string (43 characters, 256 bits of entropy)
    
    Example:
        >>> token = create_refresh_token()
        >>> len(token)
        43
    """
    return secrets.token_urlsafe(32)  # 32 bytes = 256 bits


def get_refresh_token_expiry() -> datetime:
    """Calculate refresh token expiration timestamp.
    
    Returns:
        Datetime in UTC timezone
    """
    return datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)


def extract_bearer_token(authorization: str | None) -> str:
    """Extract token from Authorization header.
    
    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")
    
    Returns:
        Token string
    
    Raises:
        TokenInvalidError: Missing or malformed Authorization header
    
    Example:
        >>> extract_bearer_token("Bearer abc123")
        'abc123'
    """
    if not authorization:
        raise TokenInvalidError()
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise TokenInvalidError()
    
    return parts[1]
