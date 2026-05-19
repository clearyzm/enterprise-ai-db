"""Test schema compatibility checking for dataset updates.

Run with: pytest tests/test_schema_compatibility.py -v
"""
import pytest
from app.utils.jsonschema import check_schema_compatibility, _is_type_compatible


class TestSchemaCompatibility:
    """Test schema compatibility checking."""

    def test_compatible_add_optional_field(self):
        """Adding optional field is compatible."""
        old_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"}
            }
        }
        new_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"}  # New optional field
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        assert is_compatible is True
        assert len(errors) == 0

    def test_incompatible_remove_required_field(self):
        """Removing required field is incompatible."""
        old_schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            }
        }
        new_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"}
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        assert is_compatible is False
        assert len(errors) == 2
        assert 'Required field "age" was removed' in errors
        assert 'Field "age" was removed' in errors

    def test_incompatible_change_type_narrowing(self):
        """Changing type from string to integer is incompatible."""
        old_schema = {
            "type": "object",
            "properties": {
                "order_no": {"type": "string"}
            }
        }
        new_schema = {
            "type": "object",
            "properties": {
                "order_no": {"type": "integer"}
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        assert is_compatible is False
        assert len(errors) == 1
        assert 'Field "order_no" type changed from "string" to "integer"' in errors[0]

    def test_compatible_type_widening(self):
        """Changing type from integer to number is compatible."""
        old_schema = {
            "type": "object",
            "properties": {
                "amount": {"type": "integer"}
            }
        }
        new_schema = {
            "type": "object",
            "properties": {
                "amount": {"type": "number"}
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        assert is_compatible is True
        assert len(errors) == 0

    def test_incompatible_remove_optional_field(self):
        """Removing optional field is incompatible (existing data has it)."""
        old_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"}
            }
        }
        new_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"}
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        assert is_compatible is False
        assert len(errors) == 1
        assert 'Field "email" was removed' in errors

    def test_compatible_add_required_field(self):
        """Adding required field is technically compatible (but risky)."""
        old_schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"}
            }
        }
        new_schema = {
            "type": "object",
            "required": ["name", "email"],
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"}
            }
        }
        is_compatible, errors = check_schema_compatibility(old_schema, new_schema)
        # This is compatible from schema perspective, but existing records won't have it
        # In practice, this should be handled by migration or default values
        assert is_compatible is True
        assert len(errors) == 0


class TestTypeCompatibility:
    """Test type compatibility checking."""

    def test_same_type_compatible(self):
        """Same type is always compatible."""
        assert _is_type_compatible("string", "string") is True
        assert _is_type_compatible("number", "number") is True

    def test_integer_to_number_compatible(self):
        """Integer to number is compatible (widening)."""
        assert _is_type_compatible("integer", "number") is True

    def test_to_string_compatible(self):
        """Any type to string is compatible (can stringify)."""
        assert _is_type_compatible("integer", "string") is True
        assert _is_type_compatible("number", "string") is True
        assert _is_type_compatible("boolean", "string") is True

    def test_number_to_integer_incompatible(self):
        """Number to integer is incompatible (narrowing)."""
        assert _is_type_compatible("number", "integer") is False

    def test_string_to_integer_incompatible(self):
        """String to integer is incompatible (may fail parsing)."""
        assert _is_type_compatible("string", "integer") is False

    def test_object_to_string_incompatible(self):
        """Object to string is incompatible (structural change)."""
        assert _is_type_compatible("object", "string") is False


# Example usage in integration test
"""
async def test_update_dataset_incompatible_schema_without_force(client, auth_headers, dataset_id):
    # Try to change string to integer without force
    response = await client.patch(
        f"/api/v1/datasets/{dataset_id}",
        headers=auth_headers,
        json={
            "schema": {
                "type": "object",
                "required": ["order_no"],
                "properties": {
                    "order_no": {"type": "integer"}  # Was string before
                }
            }
        }
    )
    assert response.status_code == 422
    assert "not backward compatible" in response.json()["message"]
    assert "order_no" in response.json()["message"]


async def test_update_dataset_incompatible_schema_with_force(client, auth_headers, dataset_id):
    # Allow breaking change with force=true
    response = await client.patch(
        f"/api/v1/datasets/{dataset_id}",
        headers=auth_headers,
        json={
            "schema": {
                "type": "object",
                "required": ["order_no"],
                "properties": {
                    "order_no": {"type": "integer"}
                }
            },
            "force": true
        }
    )
    assert response.status_code == 200
    assert response.json()["schema"]["properties"]["order_no"]["type"] == "integer"
"""
