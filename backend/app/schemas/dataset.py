"""Pydantic schemas for DataSet API validation and serialization.

Request/Response models for dataset CRUD operations.
"""
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.dataset import DataSetSensitivity, DataSetStatus


# ============================================================================
# Request Models
# ============================================================================


class CreateDataSetRequest(BaseModel):
    """Create dataset request body.
    
    Example:
        {
            "name": "Sales Orders",
            "description": "Customer order records",
            "schema": {
                "type": "object",
                "required": ["order_no", "amount"],
                "properties": {
                    "order_no": {"type": "string", "pattern": "^[A-Z]{2}\\d{8}$"},
                    "amount": {"type": "number", "minimum": 0},
                    "customer": {"type": "string", "maxLength": 200}
                },
                "additionalProperties": false
            },
            "ui_config": {
                "columns": [
                    {"field": "order_no", "label": "Order No.", "width": 120},
                    {"field": "amount", "label": "Amount", "width": 100}
                ]
            },
            "owner_dept_id": "uuid-here",
            "workflow_id": null,
            "sensitivity": "internal"
        }
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Dataset name (unique per tenant)",
    )

    description: str | None = Field(
        None,
        max_length=2000,
        description="Human-readable description",
    )

    schema: dict[str, Any] = Field(
        ...,
        description="JSON Schema for payload validation",
    )

    ui_config: dict[str, Any] = Field(
        default_factory=dict,
        description="UI display configuration (columns, sorting, actions)",
    )

    indexes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Business field indexes configuration",
    )

    owner_dept_id: str | None = Field(
        None,
        description="Owning department UUID (nullable)",
    )

    workflow_id: str | None = Field(
        None,
        description="Default workflow UUID (Phase 5+)",
    )

    sensitivity: DataSetSensitivity = Field(
        default=DataSetSensitivity.internal,
        description="Data sensitivity level",
    )

    ai_indexed: bool = Field(
        default=True,
        description="Whether to create vector embeddings for AI search",
    )

    @field_validator("schema")
    @classmethod
    def validate_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate that schema is a valid JSON Schema object."""
        if not isinstance(v, dict):
            raise ValueError("schema must be a JSON object")
        
        if v.get("type") != "object":
            raise ValueError("schema.type must be 'object'")
        
        if "properties" not in v:
            raise ValueError("schema must have 'properties' field")
        
        if not isinstance(v["properties"], dict):
            raise ValueError("schema.properties must be an object")
        
        return v

    @field_validator("indexes")
    @classmethod
    def validate_indexes(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate indexes configuration."""
        for idx in v:
            if not isinstance(idx, dict):
                raise ValueError("Each index must be an object")
            
            # Must have either 'field' or 'fields'
            if "field" not in idx and "fields" not in idx:
                raise ValueError("Index must have 'field' or 'fields'")
            
            # Validate index type if present
            if "type" in idx and idx["type"] not in ["btree", "hash", "gin", "trigram", "unique"]:
                raise ValueError(f"Invalid index type: {idx['type']}")
        
        return v


class UpdateDataSetRequest(BaseModel):
    """Update dataset request body.
    
    All fields are optional. Schema changes trigger re-indexing.
    """

    name: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        description="Dataset name",
    )

    description: str | None = Field(
        None,
        max_length=2000,
        description="Human-readable description",
    )

    schema: dict[str, Any] | None = Field(
        None,
        description="JSON Schema (triggers re-indexing if changed)",
    )

    ui_config: dict[str, Any] | None = Field(
        None,
        description="UI display configuration",
    )

    indexes: list[dict[str, Any]] | None = Field(
        None,
        description="Business field indexes configuration",
    )

    owner_dept_id: str | None = Field(
        None,
        description="Owning department UUID",
    )

    workflow_id: str | None = Field(
        None,
        description="Default workflow UUID",
    )

    sensitivity: DataSetSensitivity | None = Field(
        None,
        description="Data sensitivity level",
    )

    ai_indexed: bool | None = Field(
        None,
        description="Whether to create vector embeddings",
    )

    status: DataSetStatus | None = Field(
        None,
        description="Dataset status",
    )

    force: bool = Field(
        False,
        description="Allow breaking schema changes (default: false)",
    )

    @field_validator("schema")
    @classmethod
    def validate_schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate schema if provided."""
        if v is None:
            return v
        
        if not isinstance(v, dict):
            raise ValueError("schema must be a JSON object")
        
        if v.get("type") != "object":
            raise ValueError("schema.type must be 'object'")
        
        if "properties" not in v:
            raise ValueError("schema must have 'properties' field")
        
        return v

    @field_validator("indexes")
    @classmethod
    def validate_indexes(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Validate indexes if provided."""
        if v is None:
            return v
        
        for idx in v:
            if not isinstance(idx, dict):
                raise ValueError("Each index must be an object")
            
            if "field" not in idx and "fields" not in idx:
                raise ValueError("Index must have 'field' or 'fields'")
        
        return v


class ValidatePayloadRequest(BaseModel):
    """Validate a payload against dataset schema without persisting.
    
    Used for client-side validation before submission.
    """

    payload: dict[str, Any] = Field(
        ...,
        description="Data payload to validate",
    )


# ============================================================================
# Response Models
# ============================================================================


class DataSetResponse(BaseModel):
    """Dataset response model."""

    id: str
    tenant_id: str
    name: str
    description: str | None
    schema: dict[str, Any]
    ui_config: dict[str, Any]
    indexes: list[dict[str, Any]]
    owner_dept_id: str | None
    workflow_id: str | None
    ai_indexed: bool
    sensitivity: str
    status: str
    created_by: str | None
    created_at: str
    updated_at: str
    
    # Optional expanded relationships
    owner_department: dict[str, Any] | None = None
    creator: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "660e8400-e29b-41d4-a716-446655440000",
                "name": "Sales Orders",
                "description": "Customer order records",
                "schema": {
                    "type": "object",
                    "required": ["order_no", "amount"],
                    "properties": {
                        "order_no": {"type": "string"},
                        "amount": {"type": "number"}
                    }
                },
                "ui_config": {"columns": []},
                "indexes": [],
                "owner_dept_id": None,
                "workflow_id": None,
                "ai_indexed": True,
                "sensitivity": "internal",
                "status": "active",
                "created_by": "770e8400-e29b-41d4-a716-446655440000",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }
    }


class DataSetListResponse(BaseModel):
    """Dataset list response model."""

    datasets: list[DataSetResponse]
    total: int


class ValidatePayloadResponse(BaseModel):
    """Payload validation response."""

    valid: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "valid": True,
                    "errors": []
                },
                {
                    "valid": False,
                    "errors": [
                        {
                            "field": "order_no",
                            "message": "Does not match pattern '^[A-Z]{2}\\d{8}$'"
                        },
                        {
                            "field": "amount",
                            "message": "Must be >= 0"
                        }
                    ]
                }
            ]
        }
    }


class ImportTaskResponse(BaseModel):
    """Import task response (async job)."""

    task_id: str
    status: str = "pending"
    message: str = "Import task queued"

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": "880e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "Import task queued"
            }
        }
    }


class ExportTaskResponse(BaseModel):
    """Export task response (async job)."""

    task_id: str
    status: str = "pending"
    message: str = "Export task queued"

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": "990e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "Export task queued"
            }
        }
    }
