"""Celery background tasks for async operations.

Tasks:
- index_record: Index a single record after it's applied
- reembed_dataset: Re-index all records in a dataset after schema change
- cleanup_old_chunks: Periodic cleanup of orphaned chunks
- import_records_batch: Batch import from CSV/XLSX/JSON (Phase 4+)
- export_records_batch: Batch export to file (Phase 4+)
"""
from uuid import UUID
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, delete, text
from celery import Task

from app.workers.celery_app import celery_app, get_async_session
from app.ai.indexer import Indexer
from app.models.dataset import DataSet, DataSetStatus
from app.models.record import DataRecord, RecordStatus

logger = structlog.get_logger(__name__)


class AsyncTask(Task):
    """Base task class that handles async context properly."""
    
    def __call__(self, *args, **kwargs):
        """Execute task in async context."""
        import asyncio
        return asyncio.run(self.run_async(*args, **kwargs))
    
    async def run_async(self, *args, **kwargs):
        """Override this method in subclasses."""
        raise NotImplementedError


@celery_app.task(
    name="app.workers.tasks.index_record",
    bind=True,
    base=AsyncTask,
    max_retries=3,
    default_retry_delay=60,  # Retry after 1 minute
)
async def index_record(self: AsyncTask, record_id: str) -> dict[str, int]:
    """Index a single record: generate chunks and embeddings.
    
    Triggered when record_versions.state becomes 'applied'.
    
    Args:
        record_id: Record UUID as string
        
    Returns:
        Dict with indexing results: {"chunks_created": N}
        
    Raises:
        Retry: If indexing fails (network error, API rate limit, etc.)
    """
    logger.info("task.index_record.start", record_id=record_id)
    
    try:
        async with get_async_session() as session:
            indexer = Indexer(session)
            chunks_count = await indexer.index_record(UUID(record_id))
            await session.commit()
            
            logger.info(
                "task.index_record.complete",
                record_id=record_id,
                chunks_created=chunks_count,
            )
            
            return {"chunks_created": chunks_count}
    
    except Exception as exc:
        logger.error(
            "task.index_record.failed",
            record_id=record_id,
            error=str(exc),
            retry_count=self.request.retries,
        )
        
        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        
        # Give up after max retries
        logger.error(
            "task.index_record.gave_up",
            record_id=record_id,
            error=str(exc),
        )
        return {"chunks_created": 0, "error": str(exc)}


@celery_app.task(
    name="app.workers.tasks.reembed_dataset",
    bind=True,
    base=AsyncTask,
    max_retries=1,
    time_limit=3600,  # 1 hour for large datasets
)
async def reembed_dataset(self: AsyncTask, dataset_id: str) -> dict[str, int]:
    """Re-index all records in a dataset after schema change.
    
    Triggered when dataset.schema is updated.
    
    Args:
        dataset_id: Dataset UUID as string
        
    Returns:
        Dict with results: {"records_processed": N, "chunks_created": M}
        
    Process:
        1. Set dataset.status = 'migrating'
        2. Load all active records
        3. For each record, call indexer.index_record()
        4. Set dataset.status = 'active'
    """
    logger.info("task.reembed_dataset.start", dataset_id=dataset_id)
    
    try:
        async with get_async_session() as session:
            # Load dataset
            stmt = select(DataSet).where(DataSet.id == UUID(dataset_id))
            result = await session.execute(stmt)
            dataset = result.scalar_one_or_none()
            
            if not dataset:
                logger.warning("task.reembed_dataset.not_found", dataset_id=dataset_id)
                return {"records_processed": 0, "chunks_created": 0}
            
            # Set status to migrating
            dataset.status = DataSetStatus.migrating
            await session.commit()
            
            logger.info(
                "task.reembed_dataset.migrating",
                dataset_id=dataset_id,
                dataset_name=dataset.name,
            )
            
            # Load all active records in this dataset
            stmt = select(DataRecord).where(
                DataRecord.dataset_id == UUID(dataset_id),
                DataRecord.status == RecordStatus.active,
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
            
            logger.info(
                "task.reembed_dataset.records_loaded",
                dataset_id=dataset_id,
                records_count=len(records),
            )
            
            # Index each record
            indexer = Indexer(session)
            total_chunks = 0
            processed = 0
            
            for record in records:
                try:
                    chunks_count = await indexer.index_record(record.id)
                    total_chunks += chunks_count
                    processed += 1
                    
                    # Commit every 10 records to avoid long transactions
                    if processed % 10 == 0:
                        await session.commit()
                        logger.debug(
                            "task.reembed_dataset.progress",
                            dataset_id=dataset_id,
                            processed=processed,
                            total=len(records),
                        )
                
                except Exception as exc:
                    logger.error(
                        "task.reembed_dataset.record_failed",
                        dataset_id=dataset_id,
                        record_id=str(record.id),
                        error=str(exc),
                    )
                    # Continue with next record
                    continue
            
            # Final commit
            await session.commit()
            
            # Set status back to active
            dataset.status = DataSetStatus.active
            await session.commit()
            
            logger.info(
                "task.reembed_dataset.complete",
                dataset_id=dataset_id,
                records_processed=processed,
                chunks_created=total_chunks,
            )
            
            return {
                "records_processed": processed,
                "chunks_created": total_chunks,
            }
    
    except Exception as exc:
        logger.error(
            "task.reembed_dataset.failed",
            dataset_id=dataset_id,
            error=str(exc),
        )
        
        # Try to reset dataset status
        try:
            async with get_async_session() as session:
                stmt = select(DataSet).where(DataSet.id == UUID(dataset_id))
                result = await session.execute(stmt)
                dataset = result.scalar_one_or_none()
                if dataset:
                    dataset.status = DataSetStatus.active
                    await session.commit()
        except Exception:
            pass
        
        raise


@celery_app.task(
    name="app.workers.tasks.cleanup_old_chunks",
    bind=True,
    base=AsyncTask,
)
async def cleanup_old_chunks(self: AsyncTask, retention_hours: int = 24) -> dict[str, int]:
    """Clean up old chunks that are no longer referenced.
    
    This is a maintenance task that runs periodically (e.g., daily via cron).
    
    Args:
        retention_hours: Keep old chunks for this many hours before deletion (default 24)
        
    Returns:
        Dict with cleanup results: {"deleted_count": N}
        
    Process:
        1. Find chunks where source_version < record.version
        2. AND embedded_at < now() - retention_hours
        3. Delete those chunks
    """
    logger.info("task.cleanup_old_chunks.start", retention_hours=retention_hours)
    
    try:
        async with get_async_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
            
            # Delete old chunks using raw SQL for efficiency
            result = await session.execute(
                text("""
                    DELETE FROM chunks
                    WHERE id IN (
                        SELECT c.id
                        FROM chunks c
                        INNER JOIN data_records r ON c.record_id = r.id
                        WHERE c.source_version < r.version
                          AND c.embedded_at < :cutoff_time
                    )
                """),
                {"cutoff_time": cutoff_time},
            )
            
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(
                "task.cleanup_old_chunks.complete",
                deleted_count=deleted_count,
                retention_hours=retention_hours,
            )
            
            return {"deleted_count": deleted_count}
    
    except Exception as exc:
        logger.error(
            "task.cleanup_old_chunks.failed",
            error=str(exc),
        )
        raise


@celery_app.task(name="app.workers.tasks.import_records_batch")
def import_records_batch(dataset_id: str, file_path: str, user_id: str) -> dict:
    """Import records from CSV/XLSX/JSON file.
    
    Args:
        dataset_id: Dataset UUID (as string)
        file_path: Path to uploaded file
        user_id: User UUID who initiated import
    
    Returns:
        Dict with import results:
        {
            "total": 100,
            "success": 95,
            "failed": 5,
            "errors": [{"row": 10, "error": "Invalid order_no"}]
        }
    
    Process:
        1. Parse file (CSV/XLSX/JSON)
        2. For each row:
            a. Validate against dataset schema
            b. Create record_version (op='insert', state='pending')
            c. If workflow configured, start approval process
        3. Return summary
    
    Note:
        Phase 7: Placeholder only (TODO Phase 8+)
    """
    logger.info(
        "task.import_records_batch.placeholder",
        dataset_id=dataset_id,
        file_path=file_path,
        user_id=user_id,
    )
    # TODO Phase 8+: Implement batch import
    return {"total": 0, "success": 0, "failed": 0, "errors": []}


@celery_app.task(name="app.workers.tasks.export_records_batch")
def export_records_batch(dataset_id: str, format: str, user_id: str) -> str:
    """Export dataset records to file.
    
    Args:
        dataset_id: Dataset UUID (as string)
        format: Export format (csv/xlsx/json)
        user_id: User UUID who initiated export
    
    Returns:
        Download URL for generated file
    
    Process:
        1. Load all active records in dataset
        2. Apply permission filtering (user's accessible records only)
        3. Generate file in requested format
        4. Upload to S3 or temp storage
        5. Return download URL (expires in 1 hour)
    
    Note:
        Phase 7: Placeholder only (TODO Phase 8+)
    """
    logger.info(
        "task.export_records_batch.placeholder",
        dataset_id=dataset_id,
        format=format,
        user_id=user_id,
    )
    # TODO Phase 8+: Implement export
    return "https://example.com/download/placeholder.csv"
