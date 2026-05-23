from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if get_settings().APP_DEBUG else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger: structlog.BoundLogger = structlog.get_logger()


async def _stale_connection_cleanup() -> None:
    """Background task: evict WebSocket connections that missed ping timeout."""
    from app.realtime.ws_manager import get_ws_manager
    manager = get_ws_manager()
    while True:
        await asyncio.sleep(30)
        try:
            await manager.cleanup_stale_connections()
        except Exception as e:
            logger.warning("ws.cleanup_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("startup", env=get_settings().APP_ENV)
    # Start background task for stale WebSocket connection cleanup
    cleanup_task = asyncio.create_task(_stale_connection_cleanup())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Enterprise AI Database",
        version="0.1.0",
        description="Multi-tenant SaaS data platform with permission-aware AI assistant",
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"] if settings.APP_ENV == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Middleware — Phase 2: Tenant context for RLS
    # ------------------------------------------------------------------
    from app.middleware.tenant import TenantContextMiddleware

    application.add_middleware(TenantContextMiddleware)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @application.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    # Phase 2: Authentication and user management
    from app.api.auth import router as auth_router
    from app.api.users import router as users_router
    from app.api.roles import router as roles_router
    from app.api.departments import router as departments_router

    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(roles_router, prefix="/api/v1")
    application.include_router(departments_router, prefix="/api/v1")

    # Phase 3: DataSet management
    from app.api.datasets import router as datasets_router

    application.include_router(datasets_router, prefix="/api/v1")

    # Phase 4: DataRecord management
    from app.api.records import router as records_router
    from app.api.records import record_router

    application.include_router(records_router, prefix="/api/v1")
    application.include_router(record_router, prefix="/api/v1")

    # Phase 5: Workflow and Approval management
    from app.api.workflow import router as workflow_router
    from app.api.approvals import router as approvals_router

    application.include_router(workflow_router, prefix="/api/v1")
    application.include_router(approvals_router, prefix="/api/v1")

    # Phase 6: WebSocket real-time
    from app.api.ws import router as ws_router

    application.include_router(ws_router)

    # Phase 8: AI chat and conversation management
    from app.api.ai import router as ai_router

    application.include_router(ai_router, prefix="/api/v1")

    # Phase 9: Audit log
    from app.api.audit import router as audit_router

    application.include_router(audit_router, prefix="/api/v1")

    # ------------------------------------------------------------------
    # Exception handlers — Phase 2: APIError handling
    # ------------------------------------------------------------------
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from app.utils.errors import APIError

    @application.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        """Handle all APIError exceptions with consistent JSON response."""
        logger.error(
            "api_error",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            path=request.url.path,
            method=request.method,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(include_detail=settings.APP_DEBUG),
        )

    # ------------------------------------------------------------------
    # Exception handlers — unhandled exceptions → CORS-safe 500
    # ------------------------------------------------------------------
    # Why explicit add_exception_handler over @decorator:
    # BaseHTTPMiddleware (e.g. TenantContextMiddleware) can short-circuit
    # Starlette's ExceptionMiddleware lookup for app-level @exception_handler.
    # See encode/starlette#1582. Explicit registration via add_exception_handler
    # plus registering specific base classes (SQLAlchemyError, ValidationError)
    # ensures every escaped exception still returns a JSONResponse, so the CORS
    # middleware can add Access-Control-Allow-Origin and the frontend sees a
    # real HTTP status instead of a misleading "Failed to fetch + CORS error".

    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception(
            "unhandled_sqlalchemy_error",
            path=request.url.path,
            method=request.method,
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Database error",
                "error_type": type(exc).__name__,
                "message": str(exc),  # TODO: hide in production
            },
        )

    async def pydantic_validation_error_handler(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        logger.exception(
            "unhandled_pydantic_validation",
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "error_type": "ValidationError",
                "errors": exc.errors() if hasattr(exc, "errors") else [],
                "message": str(exc),  # TODO: hide in production
            },
        )

    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        if isinstance(exc, StarletteHTTPException):
            raise exc
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
                "message": str(exc),  # TODO: hide in production
            },
        )

    # Order matters less for add_exception_handler (FastAPI resolves by exact
    # type + MRO), but registering most-specific first is clearer.
    application.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    application.add_exception_handler(PydanticValidationError, pydantic_validation_error_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    return application


app = create_app()
