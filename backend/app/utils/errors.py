"""Unified error handling for API responses.

All API errors inherit from APIError and return consistent JSON structure:
{
  "code": "error_code",
  "message": "User-friendly message",
  "detail": {...}  // Optional, only in debug mode
}

Internal logs (structlog) contain full stack traces and context.
"""
from typing import Any


class APIError(Exception):
    """Base class for all API errors.
    
    Attributes:
        code: Machine-readable error code (e.g., 'auth.invalid_credentials')
        message: User-friendly error message (safe to expose)
        status_code: HTTP status code
        detail: Optional additional context (only exposed in debug mode)
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)

    def to_dict(self, include_detail: bool = False) -> dict[str, Any]:
        """Convert to JSON-serializable dict.
        
        Args:
            include_detail: Whether to include detail field (only in debug mode)
        
        Returns:
            Dict with code, message, and optionally detail
        """
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if include_detail and self.detail:
            result["detail"] = self.detail
        return result


# ============================================================================
# Authentication & Authorization Errors (401, 403)
# ============================================================================


class AuthenticationError(APIError):
    """Authentication failed (401)."""

    def __init__(self, message: str = "Authentication failed", detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="auth.authentication_failed",
            message=message,
            status_code=401,
            detail=detail,
        )


class InvalidCredentialsError(APIError):
    """Invalid email or password (401)."""

    def __init__(self) -> None:
        super().__init__(
            code="auth.invalid_credentials",
            message="Invalid email or password",
            status_code=401,
        )


class TokenExpiredError(APIError):
    """Access token expired (401)."""

    def __init__(self) -> None:
        super().__init__(
            code="auth.token_expired",
            message="Access token has expired",
            status_code=401,
        )


class TokenInvalidError(APIError):
    """Invalid or malformed token (401)."""

    def __init__(self) -> None:
        super().__init__(
            code="auth.token_invalid",
            message="Invalid or malformed token",
            status_code=401,
        )


class PermissionDeniedError(APIError):
    """Insufficient permissions (403)."""

    def __init__(self, message: str = "Permission denied", detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="auth.permission_denied",
            message=message,
            status_code=403,
            detail=detail,
        )


# ============================================================================
# Resource Errors (404, 409)
# ============================================================================


class NotFoundError(APIError):
    """Resource not found (404)."""

    def __init__(self, resource: str = "Resource", detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="resource.not_found",
            message=f"{resource} not found",
            status_code=404,
            detail=detail,
        )


class ConflictError(APIError):
    """Resource conflict (409), e.g., duplicate email, version conflict."""

    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "resource.conflict",
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=409,
            detail=detail,
        )


# ============================================================================
# Validation Errors (400, 422)
# ============================================================================


class ValidationError(APIError):
    """Request validation failed (422)."""

    def __init__(self, message: str = "Validation failed", detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="validation.failed",
            message=message,
            status_code=422,
            detail=detail,
        )


class InvalidScopeError(APIError):
    """Invalid permission scope (400)."""

    def __init__(self, message: str = "Invalid permission scope") -> None:
        super().__init__(
            code="validation.invalid_scope",
            message=message,
            status_code=400,
        )


# ============================================================================
# Rate Limiting (429)
# ============================================================================


class RateLimitError(APIError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(
            code="rate_limit.exceeded",
            message=message,
            status_code=429,
        )


# ============================================================================
# Internal Errors (500)
# ============================================================================


class InternalError(APIError):
    """Internal server error (500).
    
    Use this for unexpected errors. Full stack trace is logged internally,
    but only generic message is exposed to client.
    """

    def __init__(self, message: str = "Internal server error", detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="internal.error",
            message=message,
            status_code=500,
            detail=detail,
        )
class NotImplementedError(APIError):
    """Feature not implemented (501)."""
    def __init__(self, message: str = "Not implemented", detail: dict | None = None) -> None:
        super().__init__(
            code="not_implemented",
            message=message,
            status_code=501,
            detail=detail,
        )
