/**
 * JSON Diff Viewer Component
 * 
 * Features:
 * - Field-level diff highlighting for JSON objects
 * - Shows added fields (green), removed fields (red), modified fields (yellow)
 * - Handles nested objects and arrays
 * - Special handling for insert/update/delete operations
 */

import React from 'react';

// ============================================================================
// Types
// ============================================================================

interface DiffViewerProps {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  operation: 'insert' | 'update' | 'delete';
}

type DiffType = 'added' | 'removed' | 'modified' | 'unchanged';

interface FieldDiff {
  key: string;
  type: DiffType;
  beforeValue: unknown;
  afterValue: unknown;
}

// ============================================================================
// Component
// ============================================================================

export default function DiffViewer({ before, after, operation }: DiffViewerProps) {
  // For insert operation, only show after payload
  if (operation === 'insert') {
    return (
      <div className="space-y-2">
        <div className="text-sm font-medium text-gray-700 mb-2">新增记录：</div>
        {after ? (
          <div className="bg-green-50 border border-green-200 rounded-md p-4">
            <JsonDisplay data={after} />
          </div>
        ) : (
          <div className="text-sm text-gray-500">无数据</div>
        )}
      </div>
    );
  }

  // For delete operation, only show before payload
  if (operation === 'delete') {
    return (
      <div className="space-y-2">
        <div className="text-sm font-medium text-gray-700 mb-2">删除记录：</div>
        {before ? (
          <div className="bg-red-50 border border-red-200 rounded-md p-4">
            <JsonDisplay data={before} />
          </div>
        ) : (
          <div className="text-sm text-gray-500">无数据</div>
        )}
      </div>
    );
  }

  // For update operation, show diff
  if (!before || !after) {
    return (
      <div className="text-sm text-gray-500">
        无法比较：缺少变更前或变更后的数据
      </div>
    );
  }

  const diffs = computeDiff(before, after);

  if (diffs.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        无变更
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-gray-700 mb-2">字段变更：</div>
      <div className="border border-gray-200 rounded-md overflow-hidden">
        {diffs.map((diff, index) => (
          <DiffRow key={diff.key} diff={diff} isLast={index === diffs.length - 1} />
        ))}
      </div>
      <div className="flex items-center space-x-4 text-xs text-gray-500 mt-4">
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-green-100 border border-green-300 rounded"></div>
          <span>新增</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-red-100 border border-red-300 rounded"></div>
          <span>删除</span>
        </div>
        <div className="flex items-center space-x-1">
          <div className="w-3 h-3 bg-yellow-100 border border-yellow-300 rounded"></div>
          <span>修改</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Helper Components
// ============================================================================

function DiffRow({ diff, isLast }: { diff: FieldDiff; isLast: boolean }) {
  const bgColor = {
    added: 'bg-green-50',
    removed: 'bg-red-50',
    modified: 'bg-yellow-50',
    unchanged: 'bg-white',
  }[diff.type];

  const borderColor = {
    added: 'border-green-200',
    removed: 'border-red-200',
    modified: 'border-yellow-200',
    unchanged: 'border-gray-200',
  }[diff.type];

  return (
    <div className={`${bgColor} ${!isLast ? 'border-b ' + borderColor : ''} p-4`}>
      <div className="flex items-start space-x-4">
        <div className="flex-shrink-0 w-1/4">
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-900">{diff.key}</span>
            <DiffBadge type={diff.type} />
          </div>
        </div>

        <div className="flex-1 min-w-0">
          {diff.type === 'added' && (
            <div>
              <div className="text-xs text-gray-500 mb-1">新值：</div>
              <ValueDisplay value={diff.afterValue} />
            </div>
          )}

          {diff.type === 'removed' && (
            <div>
              <div className="text-xs text-gray-500 mb-1">原值：</div>
              <ValueDisplay value={diff.beforeValue} />
            </div>
          )}

          {diff.type === 'modified' && (
            <div className="space-y-2">
              <div>
                <div className="text-xs text-gray-500 mb-1">原值：</div>
                <ValueDisplay value={diff.beforeValue} strikethrough />
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">新值：</div>
                <ValueDisplay value={diff.afterValue} />
              </div>
            </div>
          )}

          {diff.type === 'unchanged' && (
            <ValueDisplay value={diff.afterValue} />
          )}
        </div>
      </div>
    </div>
  );
}

function DiffBadge({ type }: { type: DiffType }) {
  if (type === 'unchanged') return null;

  const config = {
    added: { label: '新增', color: 'bg-green-100 text-green-800' },
    removed: { label: '删除', color: 'bg-red-100 text-red-800' },
    modified: { label: '修改', color: 'bg-yellow-100 text-yellow-800' },
  };

  const { label, color } = config[type as 'added' | 'removed' | 'modified'];

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

function ValueDisplay({ value, strikethrough = false }: { value: unknown; strikethrough?: boolean }) {
  const formatted = formatValue(value);
  const className = `text-sm text-gray-900 font-mono ${strikethrough ? 'line-through text-gray-500' : ''}`;

  if (typeof value === 'object' && value !== null) {
    return (
      <pre className={`${className} whitespace-pre-wrap break-words`}>
        {formatted}
      </pre>
    );
  }

  return <span className={className}>{formatted}</span>;
}

function JsonDisplay({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="space-y-2">
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="flex items-start space-x-4">
          <div className="flex-shrink-0 w-1/4">
            <span className="text-sm font-medium text-gray-900">{key}</span>
          </div>
          <div className="flex-1 min-w-0">
            <ValueDisplay value={value} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Utility Functions
// ============================================================================

function computeDiff(before: Record<string, unknown>, after: Record<string, unknown>): FieldDiff[] {
  const diffs: FieldDiff[] = [];
  const allKeys = new Set([...Object.keys(before), ...Object.keys(after)]);

  for (const key of Array.from(allKeys).sort()) {
    const beforeValue = before[key];
    const afterValue = after[key];

    const beforeExists = key in before;
    const afterExists = key in after;

    if (!beforeExists && afterExists) {
      diffs.push({
        key,
        type: 'added',
        beforeValue: undefined,
        afterValue,
      });
    } else if (beforeExists && !afterExists) {
      diffs.push({
        key,
        type: 'removed',
        beforeValue,
        afterValue: undefined,
      });
    } else if (beforeExists && afterExists) {
      if (!isEqual(beforeValue, afterValue)) {
        diffs.push({
          key,
          type: 'modified',
          beforeValue,
          afterValue,
        });
      }
    }
  }

  return diffs;
}

function isEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null || b == null) return a === b;
  
  if (typeof a === 'object' && typeof b === 'object') {
    return JSON.stringify(a) === JSON.stringify(b);
  }
  
  return false;
}

function formatValue(value: unknown): string {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return String(value);
  
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  
  return String(value);
}
