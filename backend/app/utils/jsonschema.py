"""JSON Schema validation utilities.

Wraps jsonschema library for payload validation against dataset schemas.
Provides detailed error messages for API responses.
"""
from typing import Any

import jsonschema
from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError


class SchemaValidationError(Exception):
    """Raised when payload validation fails.
    
    Attributes:
        errors: List of validation error details
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(f"Schema validation failed with {len(errors)} error(s)")


def validate_payload(
    payload: dict[str, Any],
    schema: dict[str, Any],
    *,
    raise_on_error: bool = True,
) -> tuple[bool, list[dict[str, Any]]]:
    """Validate a payload against a JSON Schema.
    
    Args:
        payload: Data payload to validate
        schema: JSON Schema definition (must be Draft 7 compatible)
        raise_on_error: If True, raise SchemaValidationError on validation failure
    
    Returns:
        Tuple of (is_valid, errors)
        - is_valid: True if validation passed
        - errors: List of error details (empty if valid)
    
    Raises:
        SchemaValidationError: If raise_on_error=True and validation fails
        jsonschema.SchemaError: If the schema itself is invalid
    
    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "required": ["name", "age"],
        ...     "properties": {
        ...         "name": {"type": "string"},
        ...         "age": {"type": "number", "minimum": 0}
        ...     }
        ... }
        >>> payload = {"name": "Alice", "age": -5}
        >>> is_valid, errors = validate_payload(payload, schema, raise_on_error=False)
        >>> print(errors)
        [{'field': 'age', 'message': '-5 is less than the minimum of 0', 'value': -5}]
    """
    # Validate the schema itself first
    try:
        Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        # Schema definition is invalid
        raise jsonschema.SchemaError(f"Invalid JSON Schema: {e.message}") from e
    
    # Create validator
    validator = Draft7Validator(schema)
    
    # Collect all validation errors
    errors: list[dict[str, Any]] = []
    
    for error in validator.iter_errors(payload):
        errors.append(_format_validation_error(error))
    
    is_valid = len(errors) == 0
    
    if not is_valid and raise_on_error:
        raise SchemaValidationError(errors)
    
    return is_valid, errors


def _format_validation_error(error: JsonSchemaValidationError) -> dict[str, Any]:
    """Format a jsonschema ValidationError into a user-friendly dict.
    
    Args:
        error: jsonschema ValidationError instance
    
    Returns:
        Dict with field, message, and optional value/constraint info
    
    Example output:
        {
            "field": "age",
            "message": "-5 is less than the minimum of 0",
            "value": -5,
            "constraint": {"minimum": 0}
        }
    """
    # Build field path (e.g., "address.city" for nested fields)
    field_path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
    
    # Extract constraint info based on validator type
    constraint: dict[str, Any] = {}
    
    if error.validator == "required":
        # Missing required field
        constraint = {"required": error.validator_value}
    elif error.validator == "type":
        constraint = {"expected_type": error.validator_value}
    elif error.validator in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
        constraint = {error.validator: error.validator_value}
    elif error.validator == "pattern":
        constraint = {"pattern": error.validator_value}
    elif error.validator == "enum":
        constraint = {"allowed_values": error.validator_value}
    elif error.validator == "additionalProperties":
        # Extra fields not allowed
        constraint = {"additionalProperties": False}
    
    result: dict[str, Any] = {
        "field": field_path,
        "message": error.message,
    }
    
    # Include the invalid value if available
    if error.instance is not jsonschema._utils.Unset:
        result["value"] = error.instance
    
    # Include constraint details
    if constraint:
        result["constraint"] = constraint
    
    return result


def validate_schema_definition(schema: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate that a schema definition is a valid JSON Schema.
    
    Used when creating/updating datasets to ensure the schema itself is valid.
    
    Args:
        schema: JSON Schema definition to validate
    
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if schema is valid
        - error_message: Error description if invalid, None if valid
    
    Example:
        >>> schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        >>> is_valid, error = validate_schema_definition(schema)
        >>> print(is_valid)
        True
        
        >>> bad_schema = {"type": "invalid_type"}
        >>> is_valid, error = validate_schema_definition(bad_schema)
        >>> print(error)
        'Invalid JSON Schema: ...'
    """
    try:
        Draft7Validator.check_schema(schema)
        return True, None
    except jsonschema.SchemaError as e:
        return False, f"Invalid JSON Schema: {e.message}"


def get_required_fields(schema: dict[str, Any]) -> list[str]:
    """Extract required field names from a JSON Schema.
    
    Args:
        schema: JSON Schema definition
    
    Returns:
        List of required field names (empty if none)
    
    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "required": ["name", "email"],
        ...     "properties": {"name": {}, "email": {}, "age": {}}
        ... }
        >>> get_required_fields(schema)
        ['name', 'email']
    """
    return schema.get("required", [])


def get_field_type(schema: dict[str, Any], field_name: str) -> str | None:
    """Get the type of a field from a JSON Schema.
    
    Args:
        schema: JSON Schema definition
        field_name: Field name to look up
    
    Returns:
        Field type (e.g., "string", "number", "object") or None if not found
    
    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string"},
        ...         "age": {"type": "number"}
        ...     }
        ... }
        >>> get_field_type(schema, "name")
        'string'
        >>> get_field_type(schema, "unknown")
        None
    """
    properties = schema.get("properties", {})
    field_schema = properties.get(field_name, {})
    return field_schema.get("type")


def check_schema_compatibility(
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check if new schema is backward compatible with old schema.
    
    Backward compatibility rules:
    1. Cannot remove required fields
    2. Cannot change field type to a more restrictive type
    3. Can add new optional fields
    4. Can add new required fields (with caution)
    
    Args:
        old_schema: Current schema
        new_schema: Proposed new schema
    
    Returns:
        Tuple of (is_compatible, error_messages)
        - is_compatible: True if new schema is backward compatible
        - error_messages: List of compatibility issues (empty if compatible)
    
    Example:
        >>> old = {
        ...     "type": "object",
        ...     "required": ["name", "age"],
        ...     "properties": {
        ...         "name": {"type": "string"},
        ...         "age": {"type": "number"}
        ...     }
        ... }
        >>> new = {
        ...     "type": "object",
        ...     "required": ["name"],
        ...     "properties": {
        ...         "name": {"type": "integer"},
        ...         "email": {"type": "string"}
        ...     }
        ... }
        >>> is_compatible, errors = check_schema_compatibility(old, new)
        >>> print(errors)
        ['Required field "age" was removed', 'Field "name" type changed from "string" to "integer"']
    """
    errors: list[str] = []
    
    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))
    old_properties = old_schema.get("properties", {})
    new_properties = new_schema.get("properties", {})
    
    # Check 1: Required fields cannot be removed
    removed_required = old_required - new_required
    for field in removed_required:
        errors.append(f'Required field "{field}" was removed')
    
    # Check 2: Field types cannot be changed to incompatible types
    for field_name, old_field_schema in old_properties.items():
        if field_name not in new_properties:
            # Field was completely removed
            if field_name in old_required:
                # Already reported in Check 1
                pass
            else:
                # Optional field removed - this is a breaking change for existing data
                errors.append(f'Field "{field_name}" was removed')
            continue
        
        new_field_schema = new_properties[field_name]
        old_type = old_field_schema.get("type")
        new_type = new_field_schema.get("type")
        
        if old_type and new_type and old_type != new_type:
            # Type changed - check if it's compatible
            if not _is_type_compatible(old_type, new_type):
                errors.append(
                    f'Field "{field_name}" type changed from "{old_type}" to "{new_type}" '
                    f'(incompatible type change)'
                )
    
    is_compatible = len(errors) == 0
    return is_compatible, errors


def _is_type_compatible(old_type: str, new_type: str) -> bool:
    """Check if type change is backward compatible.
    
    Compatible type changes:
    - integer → number (widening)
    - Any type → string (can always stringify)
    
    Incompatible type changes:
    - string → integer (narrowing, may fail parsing)
    - number → integer (narrowing, loses decimals)
    - object → string (structural change)
    - etc.
    
    Args:
        old_type: Original field type
        new_type: New field type
    
    Returns:
        True if type change is compatible, False otherwise
    """
    # Same type is always compatible
    if old_type == new_type:
        return True
    
    # Compatible widenings
    compatible_changes = {
        ("integer", "number"),  # int can be represented as number
        ("integer", "string"),  # can stringify
        ("number", "string"),   # can stringify
        ("boolean", "string"),  # can stringify
    }
    
    return (old_type, new_type) in compatible_changes


def merge_schemas(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two JSON Schemas (for schema evolution).
    
    Combines properties from base and override schemas.
    Override takes precedence for conflicting fields.
    
    Args:
        base: Base schema
        override: Override schema (takes precedence)
    
    Returns:
        Merged schema
    
    Note:
        This is a simple merge for Phase 3. Phase 6+ will implement
        full schema evolution with compatibility checks.
    
    Example:
        >>> base = {
        ...     "type": "object",
        ...     "properties": {"name": {"type": "string"}}
        ... }
        >>> override = {
        ...     "properties": {"age": {"type": "number"}}
        ... }
        >>> merged = merge_schemas(base, override)
        >>> merged["properties"]
        {'name': {'type': 'string'}, 'age': {'type': 'number'}}
    """
    result = base.copy()
    
    # Merge properties
    if "properties" in override:
        result.setdefault("properties", {})
        result["properties"].update(override["properties"])
    
    # Merge required fields
    if "required" in override:
        base_required = set(result.get("required", []))
        override_required = set(override["required"])
        result["required"] = list(base_required | override_required)
    
    # Override other top-level fields
    for key in override:
        if key not in ("properties", "required"):
            result[key] = override[key]
    
    return result
