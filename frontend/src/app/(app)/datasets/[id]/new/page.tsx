/**
 * Create new record page.
 * 
 * Features:
 * - Dynamic form based on dataset schema
 * - Form validation with zod
 * - Submit to approval workflow
 * - Redirect to approval detail after submit
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT integrate Zod validation (no zodResolver)
 * - ❌ Does NOT implement form auto-save (draft)
 * - ❌ Does NOT implement department selector (uses default)
 * - ✅ Only implements: basic form + submit to approval
 * 
 * TODO (Phase 10+):
 * - Add Zod validation with zodResolver
 * - Add form auto-save to localStorage
 * - Add department selector dropdown
 */

'use client';

import { useState, use } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import api from '@/lib/api';
import SchemaForm from '@/components/schema-form';
import { jsonSchemaToZod, getDefaultValues } from '@/lib/jsonschema-to-zod';

// ============================================================================
// Types
// ============================================================================

interface Dataset {
  id: string;
  name: string;
  schema: Record<string, unknown>;
}

interface JSONSchema {
  type: string;
  properties?: Record<string, unknown>;
  required?: string[];
}

interface CreateRecordRequest {
  payload: Record<string, unknown>;
  department_id?: string | null;
  reason?: string | null;
}

interface SubmitRecordResponse {
  version_id: string;
  state: string;
  record: {
    id: string;
  } | null;
}

// ============================================================================
// Component
// ============================================================================

export default function NewRecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [reason, setReason] = useState('');

  // Fetch dataset
  const { data: dataset, isLoading, error } = useQuery<Dataset>({
    queryKey: ['dataset', id],
    queryFn: () => api.get<Dataset>(`/datasets/${id}`),
  });

  // Initialize form with Zod validation
  const form = useForm<Record<string, unknown>>({
    resolver: dataset ? zodResolver(jsonSchemaToZod(dataset.schema as JSONSchema)) : undefined,
    defaultValues: dataset ? getDefaultValues(dataset.schema as JSONSchema) : {},
  });

  // Create record mutation
  const createMutation = useMutation({
    mutationFn: async (data: CreateRecordRequest) => {
      return api.post<SubmitRecordResponse>(
        `/datasets/${id}/records`,
        data
      );
    },
    onSuccess: (response) => {
      // Redirect to approval detail page
      router.push(`/approvals/${response.version_id}`);
    },
  });

  // Handle form submit
  const onSubmit = form.handleSubmit(async (data) => {
    await createMutation.mutateAsync({
      payload: data,
      reason: reason || null,
    });
  });

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !dataset) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900">加载失败</h2>
          <p className="mt-2 text-gray-500">
            {error instanceof Error ? error.message : '数据集不存在或无权访问'}
          </p>
          <button
            onClick={() => router.push(`/datasets/${id}`)}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            返回数据集
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          {/* Breadcrumb */}
          <nav className="flex mb-4 text-sm">
            <Link href="/datasets" className="text-gray-500 hover:text-gray-700">
              数据集
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <Link
              href={`/datasets/${id}`}
              className="text-gray-500 hover:text-gray-700"
            >
              {dataset.name}
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-gray-900 font-medium">新增记录</span>
          </nav>

          {/* Title */}
          <h1 className="text-2xl font-bold text-gray-900">新增记录</h1>
          <p className="mt-1 text-sm text-gray-500">
            填写表单创建新记录，提交后将进入审批流程
          </p>
        </div>
      </div>

      {/* Form */}
      <div className="px-8 py-6">
        <div className="max-w-3xl">
          <form onSubmit={onSubmit} className="space-y-8">
            {/* Schema-driven fields */}
            <div className="bg-white shadow sm:rounded-lg">
              <div className="px-6 py-6">
                <h3 className="text-lg font-medium text-gray-900 mb-6">记录数据</h3>
                <SchemaForm
                  schema={dataset.schema as { type: string; properties?: Record<string, unknown>; required?: string[] }}
                  form={form}
                  disabled={createMutation.isPending}
                />
              </div>
            </div>

            {/* Reason field */}
            <div className="bg-white shadow sm:rounded-lg">
              <div className="px-6 py-6">
                <h3 className="text-lg font-medium text-gray-900 mb-6">提交说明</h3>
                <div>
                  <label htmlFor="reason" className="block text-sm font-medium text-gray-700">
                    创建原因（可选）
                  </label>
                  <textarea
                    id="reason"
                    rows={3}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    disabled={createMutation.isPending}
                    className="mt-2 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
                    placeholder="说明创建此记录的原因..."
                  />
                </div>
              </div>
            </div>

            {/* Error message */}
            {createMutation.error && (
              <div className="rounded-md bg-red-50 p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg
                      className="h-5 w-5 text-red-400"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-red-800">
                      {createMutation.error instanceof Error
                        ? createMutation.error.message
                        : '提交失败，请稍后重试'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-end space-x-4">
              <button
                type="button"
                onClick={() => router.push(`/datasets/${id}`)}
                disabled={createMutation.isPending}
                className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending ? '提交中...' : '提交审批'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
