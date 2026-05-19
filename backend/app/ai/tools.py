"""Agent tools with permission-based dynamic registration."""
from typing import Any, Callable
from uuid import UUID
import re

import structlog
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import DataSet
from app.models.record import DataRecord, RecordStatus
from app.models.user import User
from app.services.permission_service import PermissionService
from app.ai.retriever import retrieve_by_query_text

logger = structlog.get_logger(__name__)


class ToolDescriptor:
    """Tool descriptor for LangGraph agent."""
    
    def __init__(self, name: str, description: str, parameters: dict[str, Any], func: Callable[..., Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
    
    def __repr__(self) -> str:
        return f"<ToolDescriptor(name='{self.name}')>"


async def build_tools_for_user(user: User, tenant_id: UUID, db: AsyncSession) -> list[ToolDescriptor]:
    """Build tool list for user based on permissions."""
    permission_service = PermissionService(db)
    tools: list[ToolDescriptor] = []
    
    tools.append(_make_compute_tool())
    
    dataset_ids = await permission_service.get_accessible_dataset_ids(user)
    
    if dataset_ids:
        stmt = select(DataSet).where(DataSet.tenant_id == tenant_id, DataSet.id.in_(dataset_ids), DataSet.status == "active")
    else:
        stmt = select(DataSet).where(DataSet.tenant_id == tenant_id, DataSet.status == "active")
    
    result = await db.execute(stmt)
    datasets = result.scalars().all()
    
    logger.debug("tools.build.datasets_loaded", user_id=str(user.id), dataset_count=len(datasets))
    
    has_ai_query = False
    for dataset in datasets:
        if await permission_service.check(user, "ai_query", "dataset", dataset):
            has_ai_query = True
            break
    
    if has_ai_query:
        tools.append(_make_search_tool(user, tenant_id, db))
    
    for dataset in datasets:
        if not await permission_service.check(user, "read", "dataset", dataset):
            continue
        
        tools.append(_make_query_tool(user, tenant_id, dataset, db))
        tools.append(_make_count_tool(user, tenant_id, dataset, db))
        tools.append(_make_schema_tool(dataset))
    
    tools.append(_make_get_record_tool(user, tenant_id, db))
    
    logger.info("tools.build.complete", user_id=str(user.id), tenant_id=str(tenant_id), tool_count=len(tools))
    
    return tools


def _make_compute_tool() -> ToolDescriptor:
    async def compute(expression: str) -> dict[str, Any]:
        try:
            # Use simpleeval for safe mathematical expression evaluation
            # Only supports basic math operations, no function calls or attribute access
            from simpleeval import simple_eval
            
            if not re.match(r'^[\d\s\+\-\*\/\(\)\.\,]+$', expression):
                return {"error": "Invalid expression"}
            expression = expression.replace(",", "")
            result = simple_eval(expression)
            logger.debug("tool.compute.success", expression=expression, result=result)
            return {"result": result}
        except Exception as e:
            logger.warning("tool.compute.error", expression=expression, error=str(e))
            return {"error": f"Calculation error: {str(e)}"}
    
    return ToolDescriptor(
        name="compute",
        description="Evaluate mathematical expression safely.",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        func=compute,
    )


def _make_search_tool(user: User, tenant_id: UUID, db: AsyncSession) -> ToolDescriptor:
    async def search_records(query: str, dataset_name: str | None = None) -> dict[str, Any]:
        try:
            chunks = await retrieve_by_query_text(tenant_id=tenant_id, user=user, query_text=query, db=db, top_k=8)
            if dataset_name:
                stmt = select(DataSet).where(DataSet.tenant_id == tenant_id, DataSet.name == dataset_name)
                result = await db.execute(stmt)
                dataset = result.scalar_one_or_none()
                if dataset:
                    chunks = [c for c in chunks if c.dataset_id == dataset.id]
            chunk_dicts = [{"record_id": str(c.record_id), "text": c.text, "dataset_id": str(c.dataset_id), "score": round(c.score, 3)} for c in chunks]
            logger.info("tool.search_records.success", user_id=str(user.id), query=query, result_count=len(chunk_dicts))
            return {"chunks": chunk_dicts}
        except Exception as e:
            logger.error("tool.search_records.error", user_id=str(user.id), error=str(e))
            return {"error": str(e)}
    
    return ToolDescriptor(
        name="search_records",
        description="Search records using natural language query.",
        parameters={"type": "object", "properties": {"query": {"type": "string"}, "dataset_name": {"type": "string"}}, "required": ["query"]},
        func=search_records,
    )


def _make_query_tool(user: User, tenant_id: UUID, dataset: DataSet, db: AsyncSession) -> ToolDescriptor:
    async def query_records(filters: dict[str, Any] | None = None, sort: str | None = None, limit: int = 10) -> dict[str, Any]:
        try:
            if filters:
                filters = _sanitize_filters(filters, dataset.schema)
            limit = min(limit, 100)
            stmt = select(DataRecord).where(DataRecord.tenant_id == tenant_id, DataRecord.dataset_id == dataset.id, DataRecord.status == RecordStatus.active)
            if filters:
                for field, condition in filters.items():
                    stmt = _apply_filter(stmt, field, condition)
            if sort:
                if sort.startswith("-"):
                    stmt = stmt.order_by(text(f"payload->>'{sort[1:]}' DESC"))
                else:
                    stmt = stmt.order_by(text(f"payload->>'{sort}' ASC"))
            else:
                stmt = stmt.order_by(DataRecord.created_at.desc())
            stmt = stmt.limit(limit)
            result = await db.execute(stmt)
            records = result.scalars().all()
            record_dicts = [{"id": str(r.id), "payload": r.payload, "version": r.version} for r in records]
            logger.info("tool.query_records.success", user_id=str(user.id), dataset_name=dataset.name, result_count=len(record_dicts))
            return {"records": record_dicts, "count": len(record_dicts)}
        except Exception as e:
            logger.error("tool.query_records.error", user_id=str(user.id), dataset_name=dataset.name, error=str(e))
            return {"error": str(e)}
    
    return ToolDescriptor(
        name=f"query_records_{_sanitize_name(dataset.name)}",
        description=f"Query records from '{dataset.name}'. Fields: {_get_field_names(dataset.schema)}",
        parameters={"type": "object", "properties": {"filters": {"type": "object"}, "sort": {"type": "string"}, "limit": {"type": "integer", "default": 10}}},
        func=query_records,
    )


def _make_count_tool(user: User, tenant_id: UUID, dataset: DataSet, db: AsyncSession) -> ToolDescriptor:
    async def count_records(filters: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            if filters:
                filters = _sanitize_filters(filters, dataset.schema)
            stmt = select(func.count(DataRecord.id)).where(DataRecord.tenant_id == tenant_id, DataRecord.dataset_id == dataset.id, DataRecord.status == RecordStatus.active)
            if filters:
                for field, condition in filters.items():
                    stmt = _apply_filter(stmt, field, condition)
            result = await db.execute(stmt)
            count = result.scalar_one()
            logger.info("tool.count_records.success", user_id=str(user.id), dataset_name=dataset.name, count=count)
            return {"count": count}
        except Exception as e:
            logger.error("tool.count_records.error", user_id=str(user.id), dataset_name=dataset.name, error=str(e))
            return {"error": str(e)}
    
    return ToolDescriptor(name=f"count_records_{_sanitize_name(dataset.name)}", description=f"Count records in '{dataset.name}'.", parameters={"type": "object", "properties": {"filters": {"type": "object"}}}, func=count_records)


def _make_schema_tool(dataset: DataSet) -> ToolDescriptor:
    async def get_dataset_schema() -> dict[str, Any]:
        return {"dataset_name": dataset.name, "description": dataset.description, "fields": _get_field_names(dataset.schema), "schema": dataset.schema}
    return ToolDescriptor(name=f"get_schema_{_sanitize_name(dataset.name)}", description=f"Get schema for '{dataset.name}'.", parameters={"type": "object", "properties": {}}, func=get_dataset_schema)


def _make_get_record_tool(user: User, tenant_id: UUID, db: AsyncSession) -> ToolDescriptor:
    async def get_record(record_id: str) -> dict[str, Any]:
        try:
            stmt = select(DataRecord).where(DataRecord.tenant_id == tenant_id, DataRecord.id == UUID(record_id), DataRecord.status == RecordStatus.active)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                return {"error": "Record not found"}
            permission_service = PermissionService(db)
            has_permission = await permission_service.check(user=user, action="read", resource_type="record", resource_obj=record)
            if not has_permission:
                logger.warning("tool.get_record.permission_denied", user_id=str(user.id), record_id=record_id)
                return {"error": "Permission denied"}
            logger.info("tool.get_record.success", user_id=str(user.id), record_id=record_id)
            return {"record": {"id": str(record.id), "payload": record.payload, "version": record.version}}
        except Exception as e:
            logger.error("tool.get_record.error", user_id=str(user.id), error=str(e))
            return {"error": str(e)}
    return ToolDescriptor(name="get_record", description="Get single record by ID.", parameters={"type": "object", "properties": {"record_id": {"type": "string"}}, "required": ["record_id"]}, func=get_record)


def _sanitize_filters(filters: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    allowed_operators = {"eq", "ne", "in", "gt", "gte", "lt", "lte", "contains"}
    schema_properties = schema.get("properties", {})
    sanitized = {}
    for field, condition in filters.items():
        if field not in schema_properties:
            raise ValueError(f"Field '{field}' not in schema")
        if not isinstance(condition, dict):
            raise ValueError(f"Condition must be dict")
        for op, value in condition.items():
            if op not in allowed_operators:
                raise ValueError(f"Operator '{op}' not allowed")
            if op == "contains" and schema_properties[field].get("type") != "string":
                raise ValueError(f"'contains' only for string fields")
        sanitized[field] = condition
    return sanitized


def _apply_filter(stmt: Any, field: str, condition: dict[str, Any]) -> Any:
    for op, value in condition.items():
        if op == "eq":
            stmt = stmt.where(text(f"payload->>'{field}' = :val_{field}")).params({f"val_{field}": str(value)})
        elif op == "ne":
            stmt = stmt.where(text(f"payload->>'{field}' != :val_{field}")).params({f"val_{field}": str(value)})
        elif op == "gt":
            stmt = stmt.where(text(f"(payload->>'{field}')::numeric > :val_{field}")).params({f"val_{field}": value})
        elif op == "gte":
            stmt = stmt.where(text(f"(payload->>'{field}')::numeric >= :val_{field}")).params({f"val_{field}": value})
        elif op == "lt":
            stmt = stmt.where(text(f"(payload->>'{field}')::numeric < :val_{field}")).params({f"val_{field}": value})
        elif op == "lte":
            stmt = stmt.where(text(f"(payload->>'{field}')::numeric <= :val_{field}")).params({f"val_{field}": value})
        elif op == "contains":
            stmt = stmt.where(text(f"payload->>'{field}' ILIKE :val_{field}")).params({f"val_{field}": f"%{value}%"})
        elif op == "in":
            if not isinstance(value, list):
                raise ValueError("'in' requires list")
            placeholders = ",".join([f":val_{field}_{i}" for i in range(len(value))])
            stmt = stmt.where(text(f"payload->>'{field}' IN ({placeholders})"))
            params = {f"val_{field}_{i}": str(v) for i, v in enumerate(value)}
            stmt = stmt.params(**params)
    return stmt


def _sanitize_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def _get_field_names(schema: dict[str, Any]) -> list[str]:
    return list(schema.get("properties", {}).keys())
