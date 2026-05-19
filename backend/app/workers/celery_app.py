"""Celery application configuration for background tasks.

Celery is used for:
- AI indexing (index_record, reembed_dataset)
- Batch operations (import/export records)
- Cleanup tasks (old chunks, expired sessions)
"""
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.config import get_settings

settings = get_settings()

# Initialize Celery app
celery_app = Celery(
    "enterprise-ai-db",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],  # Auto-discover tasks
)

# Celery configuration
celery_app.conf.update(
    # Task execution
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "app.workers.tasks.index_record": {"queue": "indexing"},
        "app.workers.tasks.reembed_dataset": {"queue": "indexing"},
        "app.workers.tasks.cleanup_old_chunks": {"queue": "maintenance"},
        "app.workers.tasks.import_records_batch": {"queue": "batch"},
        "app.workers.tasks.export_records_batch": {"queue": "batch"},
    },
    
    # Task time limits
    task_time_limit=600,  # 10 minutes hard limit
    task_soft_time_limit=540,  # 9 minutes soft limit
    
    # Result backend
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store task args in result backend
    
    # Worker configuration
    worker_prefetch_multiplier=1,  # Fetch one task at a time (for long-running tasks)
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)
    
    # Retry configuration
    task_acks_late=True,  # Acknowledge task after completion (not before)
    task_reject_on_worker_lost=True,  # Requeue task if worker dies
)


# Database session management for workers
# We need to create a new async engine for each worker process
_async_engine = None
_async_session_factory = None


@worker_process_init.connect
def init_worker_process(**kwargs) -> None:
    """Initialize worker process with database connection pool.
    
    Called once per worker process on startup.
    Creates a new async engine and session factory for this process.
    """
    global _async_engine, _async_session_factory
    
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import structlog
    
    logger = structlog.get_logger(__name__)
    
    # Create async engine for this worker process
    _async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
    )
    
    # Create session factory
    _async_session_factory = async_sessionmaker(
        _async_engine,
        expire_on_commit=False,
    )
    
    logger.info("celery.worker.initialized", pid=kwargs.get("sender").pid)


@worker_process_shutdown.connect
def shutdown_worker_process(**kwargs) -> None:
    """Shutdown worker process and close database connections.
    
    Called once per worker process on shutdown.
    """
    global _async_engine
    
    import asyncio
    import structlog
    
    logger = structlog.get_logger(__name__)
    
    if _async_engine:
        # Close all connections in the pool
        asyncio.run(_async_engine.dispose())
        logger.info("celery.worker.shutdown", pid=kwargs.get("sender").pid)


def get_async_session():
    """Get async database session for Celery tasks.
    
    Returns:
        Async session factory
        
    Raises:
        RuntimeError: If called outside worker process (session factory not initialized)
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Async session factory not initialized. "
            "This function must be called from within a Celery worker process."
        )
    return _async_session_factory()
