"""Indexer — converts DataRecords into searchable chunks with embeddings.

Core responsibilities:
1. Extract text from record payloads based on dataset schema
2. Generate chunks (row-level summary + long field splits)
3. Create embeddings via Embedder
4. Upsert chunks to database with full metadata

Chunking strategy (per CONFIRMED-DECISIONS.md §2.2):
- Row-level summary chunk (always generated)
- Long text fields (>500 chars) split into ~400 token chunks
- Optional: relationship expansion (not implemented in Phase 7)
"""
from typing import Any
from uuid import UUID
from datetime import datetime

import structlog
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.dataset import DataSet
from app.models.record import DataRecord
from app.ai.embeddings import get_embedder

logger = structlog.get_logger(__name__)


class Indexer:
    """Indexer for converting records into vector-searchable chunks."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize indexer with database session.
        
        Args:
            db: Async database session
        """
        self.db = db
        self.embedder = get_embedder()

    async def index_record(self, record_id: UUID) -> int:
        """Index a single record: generate chunks and embeddings.
        
        Args:
            record_id: UUID of the record to index
            
        Returns:
            Number of chunks created
            
        Process:
            1. Load record and dataset
            2. Generate chunks (summary + long fields)
            3. Generate embeddings for all chunks
            4. Upsert chunks to database
            5. Delete old chunks (source_version < record.version)
        """
        # Load record with dataset
        stmt = select(DataRecord).where(DataRecord.id == record_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            logger.warning("indexer.record_not_found", record_id=str(record_id))
            return 0
        
        # Load dataset
        stmt = select(DataSet).where(DataSet.id == record.dataset_id)
        result = await self.db.execute(stmt)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            logger.warning("indexer.dataset_not_found", dataset_id=str(record.dataset_id))
            return 0
        
        # Skip if dataset is not AI indexed
        if not dataset.ai_indexed:
            logger.debug(
                "indexer.skip_not_indexed",
                record_id=str(record_id),
                dataset_id=str(dataset.id),
            )
            return 0
        
        logger.info(
            "indexer.start",
            record_id=str(record_id),
            dataset_name=dataset.name,
            version=record.version,
        )
        
        # Generate chunks
        chunks = self._generate_chunks(record, dataset)
        
        if not chunks:
            logger.warning("indexer.no_chunks", record_id=str(record_id))
            return 0
        
        # Extract texts for embedding
        texts = [chunk["text"] for chunk in chunks]
        
        # Generate embeddings
        embeddings = await self.embedder.embed(texts)
        
        # Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
        
        # Upsert chunks to database
        await self._upsert_chunks(chunks)
        
        # Delete old chunks (source_version < record.version)
        await self._delete_old_chunks(record_id, record.version)
        
        logger.info(
            "indexer.complete",
            record_id=str(record_id),
            chunks_count=len(chunks),
            version=record.version,
        )
        
        return len(chunks)

    def _generate_chunks(
        self,
        record: DataRecord,
        dataset: DataSet,
    ) -> list[dict[str, Any]]:
        """Generate chunks from record payload.
        
        Args:
            record: DataRecord to chunk
            dataset: Parent dataset with schema
            
        Returns:
            List of chunk dicts with keys:
            - tenant_id, dataset_id, record_id, department_id
            - sensitivity, source_field, text, source_version
        """
        chunks: list[dict[str, Any]] = []
        
        # Determine sensitivity (record-level or dataset-level)
        sensitivity = record.payload.get("_sensitivity", dataset.sensitivity.value)
        
        # Base metadata for all chunks
        base_meta = {
            "tenant_id": record.tenant_id,
            "dataset_id": record.dataset_id,
            "record_id": record.id,
            "department_id": record.department_id,
            "sensitivity": sensitivity,
            "source_version": record.version,
        }
        
        # 1. Row-level summary chunk (always generated)
        summary_text = self._render_summary(record, dataset)
        chunks.append({
            **base_meta,
            "source_field": None,  # Summary chunk has no specific field
            "text": summary_text,
        })
        
        # 2. Long text field chunks (>500 chars)
        for field_name, field_value in record.payload.items():
            # Skip internal fields
            if field_name.startswith("_"):
                continue
            
            # Only process string fields
            if not isinstance(field_value, str):
                continue
            
            # Skip short fields
            if len(field_value) <= 500:
                continue
            
            # Split long field into chunks
            field_chunks = self._split_long_field(
                field_name=field_name,
                field_value=field_value,
                dataset_name=dataset.name,
            )
            
            for chunk_text in field_chunks:
                chunks.append({
                    **base_meta,
                    "source_field": field_name,
                    "text": chunk_text,
                })
        
        return chunks

    def _render_summary(self, record: DataRecord, dataset: DataSet) -> str:
        """Render row-level summary chunk.
        
        Format: [Dataset: {name}] field1=value1; field2=value2; ...
        
        Args:
            record: DataRecord to summarize
            dataset: Parent dataset
            
        Returns:
            Human-readable summary text
        """
        parts = [f"[Dataset: {dataset.name}]"]
        
        for key, value in record.payload.items():
            # Skip internal fields
            if key.startswith("_"):
                continue
            
            # Format value based on type
            if value is None:
                formatted = "null"
            elif isinstance(value, bool):
                formatted = str(value).lower()
            elif isinstance(value, (int, float)):
                formatted = str(value)
            elif isinstance(value, str):
                # Truncate long strings in summary
                if len(value) > 100:
                    formatted = f"{value[:97]}..."
                else:
                    formatted = value
            elif isinstance(value, (list, dict)):
                # JSON-like representation
                formatted = str(value)[:100]
            else:
                formatted = str(value)[:100]
            
            parts.append(f"{key}={formatted}")
        
        # Add metadata if available
        if record.created_at:
            parts.append(f"created_at={record.created_at.strftime('%Y-%m-%d')}")
        
        return "; ".join(parts) + "."

    def _split_long_field(
        self,
        field_name: str,
        field_value: str,
        dataset_name: str,
    ) -> list[str]:
        """Split long text field into ~400 token chunks.
        
        Each chunk is prefixed with: [Dataset: {name}] field={field_name}
        
        Args:
            field_name: Name of the field
            field_value: Text content to split
            dataset_name: Dataset name for prefix
            
        Returns:
            List of chunk texts with prefixes
        """
        # Approximate: 1 token ≈ 4 characters
        # Target ~400 tokens ≈ 1600 characters per chunk
        chunk_size = 1600
        overlap = 200  # Overlap for context continuity
        
        prefix = f"[Dataset: {dataset_name}] field={field_name}\n\n"
        
        chunks: list[str] = []
        start = 0
        
        while start < len(field_value):
            end = start + chunk_size
            chunk_text = field_value[start:end]
            
            # Try to break at sentence boundary
            if end < len(field_value):
                # Look for sentence end in last 100 chars
                last_period = chunk_text.rfind("。")
                last_dot = chunk_text.rfind(". ")
                last_newline = chunk_text.rfind("\n")
                
                break_point = max(last_period, last_dot, last_newline)
                if break_point > chunk_size - 200:  # Within reasonable range
                    chunk_text = chunk_text[:break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(prefix + chunk_text.strip())
            
            # Move start with overlap
            start = end - overlap if end < len(field_value) else end
        
        return chunks

    async def _upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Upsert chunks to database.
        
        Uses PostgreSQL INSERT ... ON CONFLICT to handle duplicates.
        
        Args:
            chunks: List of chunk dicts with all required fields
        """
        if not chunks:
            return
        
        # Prepare rows for insertion
        rows = []
        for chunk in chunks:
            rows.append({
                "tenant_id": chunk["tenant_id"],
                "dataset_id": chunk["dataset_id"],
                "record_id": chunk["record_id"],
                "department_id": chunk["department_id"],
                "sensitivity": chunk["sensitivity"],
                "source_field": chunk["source_field"],
                "text": chunk["text"],
                "embedding": chunk["embedding"],
                "source_version": chunk["source_version"],
                "embedded_at": datetime.utcnow(),
            })
        
        # Use PostgreSQL INSERT ... ON CONFLICT
        # Note: chunks table has no unique constraint, so we just insert
        # Old chunks are deleted separately in _delete_old_chunks
        stmt = pg_insert(self.db.bind.dialect.get_table("chunks")).values(rows)
        
        # Execute raw SQL since we need to handle vector type
        from sqlalchemy import text
        
        for row in rows:
            await self.db.execute(
                text("""
                    INSERT INTO chunks (
                        tenant_id, dataset_id, record_id, department_id,
                        sensitivity, source_field, text, embedding,
                        source_version, embedded_at
                    ) VALUES (
                        :tenant_id, :dataset_id, :record_id, :department_id,
                        :sensitivity, :source_field, :text, :embedding::vector,
                        :source_version, :embedded_at
                    )
                """),
                row,
            )

    async def _delete_old_chunks(self, record_id: UUID, current_version: int) -> None:
        """Delete chunks from old versions of the record.
        
        Args:
            record_id: Record UUID
            current_version: Current record version (keep chunks with this version)
        """
        from sqlalchemy import text
        
        result = await self.db.execute(
            text("""
                DELETE FROM chunks
                WHERE record_id = :record_id
                  AND source_version < :current_version
            """),
            {"record_id": record_id, "current_version": current_version},
        )
        
        deleted_count = result.rowcount
        
        if deleted_count > 0:
            logger.debug(
                "indexer.deleted_old_chunks",
                record_id=str(record_id),
                deleted_count=deleted_count,
            )
