/**
 * Convert JSON Schema to Zod schema for form validation.
 * 
 * Supports:
 * - string (with minLength, maxLength, pattern)
 * - number/integer (with minimum, maximum)
 * - boolean
 * - enum
 * 
 * Not supported (Phase 9 v1):
 * - array
 * - object (nested)
 * - $ref
 */

import { z } from 'zod';

// ============================================================================
// Types
// ============================================================================

interface JSONSchema {
  type: string;
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
}

interface JSONSchemaProperty {
  type: string;
  title?: string;
  description?: string;
  enum?: Array<string | number>;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  default?: unknown;
}

// ============================================================================
// Main Function
// ============================================================================

/**
 * Convert JSON Schema to Zod schema.
 * 
 * @param schema - JSON Schema object
 * @returns Zod schema for validation
 */
export function jsonSchemaToZod(schema: JSONSchema): z.ZodObject<Record<string, z.ZodTypeAny>> {
  if (schema.type !== 'object') {
    throw new Error('Root schema must be of type "object"');
  }

  if (!schema.properties) {
    throw new Error('Schema must have "properties" field');
  }

  const properties = schema.properties;
  const required = schema.required || [];
  const zodShape: Record<string, z.ZodTypeAny> = {};

  // Convert each property
  for (const [fieldName, fieldSchema] of Object.entries(properties)) {
    const isRequired = required.includes(fieldName);
    let zodField = convertProperty(fieldName, fieldSchema);

    // Make optional if not required
    if (!isRequired) {
      zodField = zodField.optional();
    }

    zodShape[fieldName] = zodField;
  }

  return z.object(zodShape);
}

// ============================================================================
// Property Converters
// ============================================================================

/**
 * Convert a single JSON Schema property to Zod type.
 */
function convertProperty(fieldName: string, fieldSchema: JSONSchemaProperty): z.ZodTypeAny {
  // Enum type (takes precedence)
  if (fieldSchema.enum && fieldSchema.enum.length > 0) {
    return convertEnum(fieldSchema);
  }

  // Type-based conversion
  switch (fieldSchema.type) {
    case 'string':
      return convertString(fieldSchema);
    
    case 'number':
    case 'integer':
      return convertNumber(fieldSchema);
    
    case 'boolean':
      return convertBoolean(fieldSchema);
    
    case 'array':
      // Not supported in Phase 9 v1
      console.warn(`Field "${fieldName}": array type not supported, using z.any()`);
      return z.any();
    
    case 'object':
      // Not supported in Phase 9 v1
      console.warn(`Field "${fieldName}": nested object type not supported, using z.any()`);
      return z.any();
    
    default:
      console.warn(`Field "${fieldName}": unknown type "${fieldSchema.type}", using z.any()`);
      return z.any();
  }
}

/**
 * Convert string type to Zod.
 */
function convertString(fieldSchema: JSONSchemaProperty): z.ZodString {
  let zodString = z.string({
    required_error: `${fieldSchema.title || 'This field'} is required`,
    invalid_type_error: `${fieldSchema.title || 'This field'} must be a string`,
  });

  // Min length
  if (fieldSchema.minLength !== undefined) {
    zodString = zodString.min(
      fieldSchema.minLength,
      `Must be at least ${fieldSchema.minLength} characters`
    );
  }

  // Max length
  if (fieldSchema.maxLength !== undefined) {
    zodString = zodString.max(
      fieldSchema.maxLength,
      `Must be at most ${fieldSchema.maxLength} characters`
    );
  }

  // Pattern (regex)
  if (fieldSchema.pattern) {
    try {
      const regex = new RegExp(fieldSchema.pattern);
      zodString = zodString.regex(
        regex,
        `Must match pattern: ${fieldSchema.pattern}`
      );
    } catch (error) {
      console.warn(`Invalid regex pattern: ${fieldSchema.pattern}`);
    }
  }

  return zodString;
}

/**
 * Convert number/integer type to Zod.
 */
function convertNumber(fieldSchema: JSONSchemaProperty): z.ZodNumber {
  let zodNumber = z.number({
    required_error: `${fieldSchema.title || 'This field'} is required`,
    invalid_type_error: `${fieldSchema.title || 'This field'} must be a number`,
  });

  // Integer check
  if (fieldSchema.type === 'integer') {
    zodNumber = zodNumber.int('Must be an integer');
  }

  // Minimum
  if (fieldSchema.minimum !== undefined) {
    zodNumber = zodNumber.min(
      fieldSchema.minimum,
      `Must be at least ${fieldSchema.minimum}`
    );
  }

  // Maximum
  if (fieldSchema.maximum !== undefined) {
    zodNumber = zodNumber.max(
      fieldSchema.maximum,
      `Must be at most ${fieldSchema.maximum}`
    );
  }

  return zodNumber;
}

/**
 * Convert boolean type to Zod.
 */
function convertBoolean(fieldSchema: JSONSchemaProperty): z.ZodBoolean {
  return z.boolean({
    required_error: `${fieldSchema.title || 'This field'} is required`,
    invalid_type_error: `${fieldSchema.title || 'This field'} must be a boolean`,
  });
}

/**
 * Convert enum type to Zod.
 */
function convertEnum(fieldSchema: JSONSchemaProperty): z.ZodEnum<[string, ...string[]]> | z.ZodNumber {
  if (!fieldSchema.enum || fieldSchema.enum.length === 0) {
    throw new Error('Enum must have at least one value');
  }

  // Check if all enum values are strings
  const allStrings = fieldSchema.enum.every((val) => typeof val === 'string');
  
  if (allStrings) {
    // String enum
    const enumValues = fieldSchema.enum as string[];
    return z.enum([enumValues[0], ...enumValues.slice(1)], {
      required_error: `${fieldSchema.title || 'This field'} is required`,
      invalid_type_error: `Must be one of: ${enumValues.join(', ')}`,
    });
  } else {
    // Number enum or mixed - use union
    const literals = fieldSchema.enum.map((val) => z.literal(val));
    return z.union([literals[0], literals[1], ...literals.slice(2)] as [z.ZodLiteral<unknown>, z.ZodLiteral<unknown>, ...z.ZodLiteral<unknown>[]]);
  }
}

// ============================================================================
// Helper: Get default values from schema
// ============================================================================

/**
 * Extract default values from JSON Schema for form initialization.
 * 
 * @param schema - JSON Schema object
 * @returns Object with default values
 */
export function getDefaultValues(schema: JSONSchema): Record<string, unknown> {
  if (!schema.properties) {
    return {};
  }

  const defaults: Record<string, unknown> = {};

  for (const [fieldName, fieldSchema] of Object.entries(schema.properties)) {
    if (fieldSchema.default !== undefined) {
      defaults[fieldName] = fieldSchema.default;
    } else {
      // Set sensible defaults based on type
      switch (fieldSchema.type) {
        case 'string':
          defaults[fieldName] = '';
          break;
        case 'number':
        case 'integer':
          defaults[fieldName] = 0;
          break;
        case 'boolean':
          defaults[fieldName] = false;
          break;
        default:
          defaults[fieldName] = undefined;
      }
    }
  }

  return defaults;
}
