"""Permission-aware retrieval for AI queries.

Implements the retrieval algorithm from 04-ai-system.md §3:
1. Compute user's AI access bundle (datasets, departments, sensitivities)
2. Execute pgvector ANN search with permission filters in SQL WHERE clause
3. Apply secondary permission check on retrieved chunks' records
4. Return filtered chunks with metadata for citation

Key security requirements (from CONFIRMED-DECISIONS.md §6):
- Permission context MUST be passed as SQL WHERE conditions BEFORE vector similarity
- Every chunk's record MUST be verified with PermissionService.check after retrieval
- No chunk can be returned if user lacks 'read' permission on its record
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embedder
from app.models.user import User
from app.services.permission_service import PermissionService

logger = structlog.get_logger(__name__)


@dataclass
class Chunk:
    """Retrieved chunk with metadata for citation.
    
    Attributes:
        id: Chunk UUID
        dataset_id: Parent dataset UUID
        record_id: Source record UUID
        text: Chunk text content
        sensitivity: Sensitivity level (public/internal/confidential/restricted)
        score: Similarity score (1 - cosine_distance, range [0, 1])
        source_field: Source field name (None for summary chunks)
        department_id: Department UUID (None for tenant-wide records)
    """
    id: UUID
    dataset_id: UUID
    record_id: UUID
    text: str
    sensitivity: str
    score: float
    source_field: str | None
    department_id: UUID | None


async def permission_aware_retrieve(
    tenant_id: UUID,
    user: User,
    query_embedding: list[float],
    db: AsyncSession,
    top_k: int = 8,
) -> list[Chunk]:
    """Retrieve chunks with permission filtering.
    
    Algorithm (from 04-ai-system.md §3):
    1. Compute user's AI access bundle via PermissionService.compute_ai_access()
    2. Execute pgvector ANN search with WHERE clause filtering:
       - tenant_id = :tid
       - dataset_id = ANY(:ds) (if user has dataset scope)
       - department_id IS NULL OR department_id = ANY(:depts) (if user has dept scope)
       - sensitivity = ANY(:sensitivities)
    3. Retrieve top_k * 3 candidates (over-fetch for reranking/filtering)
    4. Secondary permission check: verify user has 'read' on each chunk's record
    5. Return filtered chunks (up to top_k)
    
    Args:
        tenant_id: Tenant UUID (from RLS context)
        user: User object (with loaded user_roles)
        query_embedding: Query embedding vector (length must match EMBED_DIM)
        db: Async database session
        top_k: Number of chunks to return (default 8)
    
    Returns:
        List of Chunk objects, sorted by similarity score (descending)
    
    Raises:
        ValueError: If query_embedding dimension doesn't match EMBED_DIM
    
    Example:
        >>> embedder = get_embedder()
        >>> query_emb = (await embedder.embed(["用户问题"]))[0]
        >>> chunks = await permission_aware_retrieve(
        ...     tenant_id=user.tenant_id,
        ...     user=user,
        ...     query_embedding=query_emb,
        ...     db=db,
        ...     top_k=8,
        ... )
    """
    # Step 1: Compute AI access bundle
    permission_service = PermissionService(db)
    access = await permission_service.compute_ai_access(user)
    
    # If user has no accessible datasets, return empty
    if access.dataset_ids is not None and len(access.dataset_ids) == 0:
        logger.info(
            "retriever.no_access",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
        )
        return []
    
    # If user has no allowed sensitivities, return empty
    if not access.allowed_sensitivities:
        logger.info(
            "retriever.no_sensitivity_access",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
        )
        return []
    
    # Validate embedding dimension
    embedder = get_embedder()
    if len(query_embedding) != embedder.dim:
        raise ValueError(
            f"Query embedding dimension {len(query_embedding)} "
            f"doesn't match EMBED_DIM {embedder.dim}"
        )
    
    # Step 2: Build SQL query with permission filters
    # Note: We over-fetch (top_k * 3) to allow for secondary filtering
    fetch_limit = top_k * 3
    
    # Build WHERE conditions based on access bundle
    where_conditions = [
        "tenant_id = :tid",
        "sensitivity = ANY(:sensitivities)",
    ]
    
    params: dict[str, Any] = {
        "tid": tenant_id,
        "sensitivities": access.allowed_sensitivities,
        "k": fetch_limit,
    }
    
    # Dataset filter (empty list = all datasets in tenant)
    if access.dataset_ids:
        where_conditions.append("dataset_id = ANY(:ds)")
        params["ds"] = [str(ds_id) for ds_id in access.dataset_ids]
    
    # Department filter (empty list = all departments in tenant)
    if access.dept_ids:
        where_conditions.append("(department_id IS NULL OR department_id = ANY(:depts))")
        params["depts"] = [str(dept_id) for dept_id in access.dept_ids]
    
    where_clause = " AND ".join(where_conditions)
    
    # SQL query: pgvector ANN search with permission filters
    # Note: 1 - (embedding <=> :q) converts distance to similarity score [0, 1]
    # nosec B608 - where_clause contains only hardcoded string constants, values are parameterized
    sql = f"""
        SELECT 
            id,
            dataset_id,
            record_id,
            text,
            sensitivity,
            source_field,
            department_id,
            1 - (embedding <=> :q::vector) AS score
        FROM chunks
        WHERE {where_clause}
        ORDER BY embedding <=> :q::vector
        LIMIT :k
    """
    
    # Convert embedding to PostgreSQL vector format
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    params["q"] = embedding_str
    
    logger.debug(
        "retriever.query.start",
        user_id=str(user.id),
        tenant_id=str(tenant_id),
        top_k=top_k,
        fetch_limit=fetch_limit,
        dataset_filter=bool(access.dataset_ids),
        dept_filter=bool(access.dept_ids),
        sensitivities=access.allowed_sensitivities,
    )
    
    # Execute query
    result = await db.execute(text(sql), params)
    rows = result.fetchall()
    
    logger.debug(
        "retriever.query.complete",
        user_id=str(user.id),
        candidates=len(rows),
    )
    
    # Step 3: Convert rows to Chunk objects
    candidates = [
        Chunk(
            id=UUID(str(row.id)),
            dataset_id=UUID(str(row.dataset_id)),
            record_id=UUID(str(row.record_id)),
            text=row.text,
            sensitivity=row.sensitivity,
            score=float(row.score),
            source_field=row.source_field,
            department_id=UUID(str(row.department_id)) if row.department_id else None,
        )
        for row in rows
    ]
    
    # Step 4: Secondary permission check on records
    # Load records and verify user has 'read' permission
    filtered_chunks: list[Chunk] = []
    record_cache: dict[UUID, Any] = {}  # Cache to avoid duplicate queries
    
    for chunk in candidates:
        # Check cache first
        if chunk.record_id not in record_cache:
            # Load record (simplified: in production, batch load for efficiency)
            record_result = await db.execute(
                text("SELECT id, dataset_id, department_id FROM data_records WHERE id = :rid"),
                {"rid": chunk.record_id},
            )
            record_row = record_result.fetchone()
            
            if not record_row:
                logger.warning(
                    "retriever.record_not_found",
                    chunk_id=str(chunk.id),
                    record_id=str(chunk.record_id),
                )
                record_cache[chunk.record_id] = None
                continue
            
            # Create minimal record object for permission check
            # Note: PermissionService._scope_matches only needs dataset_id and department_id
            record_obj = type('Record', (), {
                'id': UUID(str(record_row.id)),
                'dataset_id': UUID(str(record_row.dataset_id)),
                'department_id': UUID(str(record_row.department_id)) if record_row.department_id else None,
            })()
            
            record_cache[chunk.record_id] = record_obj
        
        record_obj = record_cache[chunk.record_id]
        if record_obj is None:
            continue
        
        # Verify 'read' permission
        has_permission = await permission_service.check(
            user=user,
            action="read",
            resource_type="record",
            resource_obj=record_obj,
        )
        
        if has_permission:
            filtered_chunks.append(chunk)
        else:
            logger.debug(
                "retriever.permission_denied",
                user_id=str(user.id),
                chunk_id=str(chunk.id),
                record_id=str(chunk.record_id),
            )
        
        # Stop if we have enough chunks
        if len(filtered_chunks) >= top_k:
            break
    
    logger.info(
        "retriever.complete",
        user_id=str(user.id),
        tenant_id=str(tenant_id),
        candidates=len(candidates),
        filtered=len(filtered_chunks),
        top_k=top_k,
    )
    
    return filtered_chunks[:top_k]


async def retrieve_by_query_text(
    tenant_id: UUID,
    user: User,
    query_text: str,
    db: AsyncSession,
    top_k: int = 8,
) -> list[Chunk]:
    """Convenience wrapper: embed query text and retrieve chunks.
    
    Args:
        tenant_id: Tenant UUID
        user: User object
        query_text: Natural language query
        db: Async database session
        top_k: Number of chunks to return
    
    Returns:
        List of Chunk objects
    
    Example:
        >>> chunks = await retrieve_by_query_text(
        ...     tenant_id=user.tenant_id,
        ...     user=user,
        ...     query_text="2024年4月销售额",
        ...     db=db,
        ... )
    """
    # Embed query text
    embedder = get_embedder()
    embeddings = await embedder.embed([query_text])
    query_embedding = embeddings[0]
    
    # Retrieve chunks
    return await permission_aware_retrieve(
        tenant_id=tenant_id,
        user=user,
        query_embedding=query_embedding,
        db=db,
        top_k=top_k,
    )
