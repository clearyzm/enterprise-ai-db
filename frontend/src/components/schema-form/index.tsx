/**
 * Dynamic form component that renders form fields based on JSON Schema.
 * 
 * Features:
 * - Supports string, number, boolean, enum types
 * - Integrates with react-hook-form
 * - Type-safe with TypeScript
 * - Renders appropriate input components based on schema
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT support `array` type (dynamic lists)
 * - ❌ Does NOT support nested `object` type
 * - ❌ Does NOT support `$ref` (references to other datasets)
 * - ❌ Does NOT support date picker (`format: "date"`)
 * - ❌ Does NOT support file upload (`format: "binary"`)
 * - ✅ Only supports: string, number, integer, boolean, enum
 * 
 * TODO (Phase 10+):
 * - Add array field support with dynamic add/remove
 * - Add nested object rendering
 * - Add reference selector for $ref fields
 * - Add date/time pickers
 */

'use client';

import { UseFormReturn } from 'react-hook-form';

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

interface SchemaFormProps {
  schema: JSONSchema;
  form: UseFormReturn<Record<string, unknown>>;
  disabled?: boolean;
}

// ============================================================================
// Main Component
// ============================================================================

export default function SchemaForm({ schema, form, disabled = false }: SchemaFormProps) {
  const { register, formState: { errors } } = form;
  const properties = schema.properties || {};
  const required = schema.required || [];

  return (
    <div className="space-y-6">
      {Object.entries(properties).map(([fieldName, fieldSchema]) => {
        const isRequired = required.includes(fieldName);
        const error = errors[fieldName];
        const errorMessage = error?.message as string | undefined;

        return (
          <div key={fieldName}>
            <label htmlFor={fieldName} className="block text-sm font-medium text-gray-700">
              {fieldSchema.title || fieldName}
              {isRequired && <span className="text-red-500 ml-1">*</span>}
            </label>
            
            {fieldSchema.description && (
              <p className="mt-1 text-xs text-gray-500">{fieldSchema.description}</p>
            )}

            <div className="mt-2">
              {renderField(fieldName, fieldSchema, register, disabled)}
            </div>

            {errorMessage && (
              <p className="mt-1 text-sm text-red-600">{errorMessage}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// Field Renderers
// ============================================================================

function renderField(
  fieldName: string,
  fieldSchema: JSONSchemaProperty,
  register: UseFormReturn<Record<string, unknown>>['register'],
  disabled: boolean
): React.ReactNode {
  // Enum → Select
  if (fieldSchema.enum && fieldSchema.enum.length > 0) {
    return (
      <select
        id={fieldName}
        {...register(fieldName)}
        disabled={disabled}
        className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
      >
        <option value="">请选择</option>
        {fieldSchema.enum.map((option) => (
          <option key={String(option)} value={String(option)}>
            {String(option)}
          </option>
        ))}
      </select>
    );
  }

  // Boolean → Switch (checkbox styled)
  if (fieldSchema.type === 'boolean') {
    return (
      <div className="flex items-center">
        <input
          id={fieldName}
          type="checkbox"
          {...register(fieldName)}
          disabled={disabled}
          className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded disabled:cursor-not-allowed"
        />
        <label htmlFor={fieldName} className="ml-2 text-sm text-gray-700">
          启用
        </label>
      </div>
    );
  }

  // Number → Number Input
  if (fieldSchema.type === 'number' || fieldSchema.type === 'integer') {
    return (
      <input
        id={fieldName}
        type="number"
        step={fieldSchema.type === 'integer' ? '1' : 'any'}
        min={fieldSchema.minimum}
        max={fieldSchema.maximum}
        {...register(fieldName, {
          valueAsNumber: true,
        })}
        disabled={disabled}
        className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
      />
    );
  }

  // String → Text Input (default)
  return (
    <input
      id={fieldName}
      type="text"
      maxLength={fieldSchema.maxLength}
      {...register(fieldName)}
      disabled={disabled}
      className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
      placeholder={fieldSchema.pattern ? `格式: ${fieldSchema.pattern}` : undefined}
    />
  );
}
