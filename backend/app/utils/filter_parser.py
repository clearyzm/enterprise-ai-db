"""Safe filter parser for JSONB payload queries.

Parses user-provided filter expressions and converts them to parameterized SQL.
Prevents SQL injection by:
1. Whitelist of allowed operators
2. Whitelist of allowed fields (from dataset.schema)
3. All values are parameterized (never string concatenation)

Filter syntax:
    ?filter=field__op=value
    
Supported operators:
    - eq: Equal (=)
    - ne: Not equal (!=)
    - gt: Greater than (>)
    - gte: Greater than or equal (>=)
    - lt: Less than (<)
    - lte: Less than or equal (<=)
    - in: In list (IN)
    - contains: String contains (ILIKE)

Examples:
    ?filter=amount__gte=100
    ?filter=status__eq=paid
    ?filter=customer__contains=Acme
    ?filter=order_no__in=AB12345678,AB12345679
"""
from typing import Any

from sqlalchemy import and_, or_, text
from sqlalchemy.sql import ColumnElement
import structlog

from app.utils.errors import ValidationError

logger = structlog.get_logger()


# Whitelist of allowed operators
ALLOWED_OPERATORS = {
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
}

# Operator to SQL mapping (for JSONB fields)
OPERATOR_SQL_MAP = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "in": "IN",
    "contains": "ILIKE",
}


class FilterParser:
    """Parse and validate filter expressions for JSONB payload queries.
    
    Usage:
        parser = FilterParser(dataset_schema)
        filters = parser.parse_filters({"amount__gte": "100", "status__eq": "paid"})
        stmt = select(DataRecord).where(and_(*filters))
    """

    def __init__(self, dataset_schema: dict[str, Any]) -> None:
        """Initialize parser with dataset schema.
        
        Args:
            dataset_schema: JSON Schema definition from dataset.schema
        """
        self.dataset_schema = dataset_schema
        self.allowed_fields = self._extract_allowed_fields(dataset_schema)
        logger.debug(
            "filter_parser_initialized",
            allowed_fields=self.allowed_fields,
        )

    def _extract_allowed_fields(self, schema: dict[str, Any]) -> set[str]:
        """Extract allowed field names from JSON Schema.
        
        Args:
            schema: JSON Schema object
            
        Returns:
            Set of allowed field names
        """
        properties = schema.get("properties", {})
        return set(properties.keys())

    def parse_filters(
        self,
        filter_params: dict[str, str],
    ) -> list[ColumnElement[bool]]:
        """Parse filter parameters into SQLAlchemy WHERE clauses.
        
        Args:
            filter_params: Dict of filter expressions (field__op: value)
            
        Returns:
            List of SQLAlchemy WHERE clause elements
            
        Raises:
            ValidationError: If filter syntax is invalid or field not allowed
            
        Example:
            >>> parser.parse_filters({"amount__gte": "100", "status__eq": "paid"})
            [<BinaryExpression>, <BinaryExpression>]
        """
        filters: list[ColumnElement[bool]] = []

        for key, value in filter_params.items():
            # Parse field__operator syntax
            if "__" not in key:
                raise ValidationError(
                    f"Invalid filter syntax: '{key}'. Expected 'field__operator' format."
                )

            parts = key.split("__")
            if len(parts) != 2:
                raise ValidationError(
                    f"Invalid filter syntax: '{key}'. Expected exactly one '__' separator."
                )

            field, operator = parts

            # Validate field is in schema
            if field not in self.allowed_fields:
                raise ValidationError(
                    f"Field '{field}' not found in dataset schema. "
                    f"Allowed fields: {sorted(self.allowed_fields)}"
                )

            # Validate operator is allowed
            if operator not in ALLOWED_OPERATORS:
                raise ValidationError(
                    f"Operator '{operator}' not allowed. "
                    f"Allowed operators: {sorted(ALLOWED_OPERATORS)}"
                )

            # Build filter clause
            filter_clause = self._build_filter_clause(field, operator, value)
            filters.append(filter_clause)

            logger.debug(
                "filter_parsed",
                field=field,
                operator=operator,
                value=value,
            )

        return filters

    def _build_filter_clause(
        self,
        field: str,
        operator: str,
        value: str,
    ) -> ColumnElement[bool]:
        """Build a parameterized SQL filter clause for JSONB field.
        
        Args:
            field: Field name (validated against schema)
            operator: Operator (validated against whitelist)
            value: Filter value (will be parameterized)
            
        Returns:
            SQLAlchemy WHERE clause element
            
        Note:
            All values are parameterized using bindparam() to prevent SQL injection.
        """
        # Get field type from schema for type coercion
        field_type = self._get_field_type(field)

        # Convert value to appropriate Python type
        typed_value = self._coerce_value(value, field_type, operator)

        # Build JSONB accessor: payload->>'field'
        # For numeric comparisons, cast to appropriate type
        if field_type in ("number", "integer") and operator not in ("contains", "in"):
            # Cast JSONB text to numeric: (payload->>'field')::numeric
            jsonb_accessor = f"(payload->>'{field}')::numeric"
        elif field_type == "boolean":
            # Cast JSONB text to boolean: (payload->>'field')::boolean
            jsonb_accessor = f"(payload->>'{field}')::boolean"
        else:
            # String comparison: payload->>'field'
            jsonb_accessor = f"payload->>'{field}'"

        # Build SQL expression with parameterized value
        if operator == "in":
            # IN operator: field IN (:value1, :value2, ...)
            # typed_value is a list
            if not isinstance(typed_value, list):
                raise ValidationError(f"Operator 'in' requires a list value")
            
            # Build IN clause with parameterized values
            placeholders = ", ".join([f":value_{i}" for i in range(len(typed_value))])
            sql_expr = f"{jsonb_accessor} IN ({placeholders})"
            
            # Create bindparams for each value
            params = {f"value_{i}": v for i, v in enumerate(typed_value)}
            return text(sql_expr).bindparams(**params)
        
        elif operator == "contains":
            # ILIKE operator: field ILIKE :value
            # Wrap value with % wildcards
            sql_expr = f"{jsonb_accessor} ILIKE :value"
            return text(sql_expr).bindparams(value=f"%{typed_value}%")
        
        else:
            # Standard comparison operators: field op :value
            sql_op = OPERATOR_SQL_MAP[operator]
            sql_expr = f"{jsonb_accessor} {sql_op} :value"
            return text(sql_expr).bindparams(value=typed_value)

    def _get_field_type(self, field: str) -> str:
        """Get JSON Schema type for a field.
        
        Args:
            field: Field name
            
        Returns:
            JSON Schema type (string, number, integer, boolean, object, array)
        """
        properties = self.dataset_schema.get("properties", {})
        field_schema = properties.get(field, {})
        return field_schema.get("type", "string")

    def _coerce_value(
        self,
        value: str,
        field_type: str,
        operator: str,
    ) -> Any:
        """Coerce string value to appropriate Python type.
        
        Args:
            value: String value from query parameter
            field_type: JSON Schema type
            operator: Filter operator
            
        Returns:
            Typed value (str, int, float, bool, list)
            
        Raises:
            ValidationError: If value cannot be coerced to expected type
        """
        try:
            if operator == "in":
                # Split comma-separated values
                values = [v.strip() for v in value.split(",")]
                # Coerce each value
                return [self._coerce_single_value(v, field_type) for v in values]
            else:
                return self._coerce_single_value(value, field_type)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                f"Cannot convert value '{value}' to type '{field_type}': {e}"
            )

    def _coerce_single_value(self, value: str, field_type: str) -> Any:
        """Coerce a single string value to appropriate Python type.
        
        Args:
            value: String value
            field_type: JSON Schema type
            
        Returns:
            Typed value
        """
        if field_type == "integer":
            return int(value)
        elif field_type == "number":
            return float(value)
        elif field_type == "boolean":
            # Accept: true/false, 1/0, yes/no
            lower = value.lower()
            if lower in ("true", "1", "yes"):
                return True
            elif lower in ("false", "0", "no"):
                return False
            else:
                raise ValueError(f"Invalid boolean value: {value}")
        else:
            # string, object, array → keep as string
            return value
