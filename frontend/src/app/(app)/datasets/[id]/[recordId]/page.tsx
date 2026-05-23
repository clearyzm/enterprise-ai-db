'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { can } from '@/lib/permissions';

interface Dataset {
  id: string;
  name: string;
  schema: {
    type: string;
    properties?: Record<string, JSONSchemaProperty>;
    required?: string[];
  };
}

interface JSONSchemaProperty {
  type: string;
  title?: string;
  description?: string;
  enum?: Array<string | number>;
  format?: string;
}

interface DataRecord {
  id: string;
  payload: Record<string, unknown>;
  version: number;
  status?: string;
  created_by?: string;
  updated_at?: string;
  has_pending_version?: boolean;
}

function formatValue(value: unknown, fieldSchema: JSONSchemaProperty): string {
  if (value === null || value === undefined || value === '') return '—';
  if (fieldSchema.type === 'boolean') return value ? '是' : '否';
  if (fieldSchema.format === 'date' || fieldSchema.format === 'date-time') {
    try { return new Date(value as string).toLocaleString('zh-CN'); } catch { return String(value); }
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

export default function ViewRecordPage({ params }: { params: Promise<{ id: string; recordId: string }> }) {
  const { id, recordId } = use(params);
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  const { data: dataset, isLoading: loadingDS, error: errorDS } = useQuery<Dataset>({
    queryKey: ['dataset', id],
    queryFn: () => api.get<Dataset>(`/datasets/${id}`),
  });

  const { data: record, isLoading: loadingRec, error: errorRec } = useQuery<DataRecord>({
    queryKey: ['record', id, recordId],
    queryFn: () => api.get<DataRecord>(`/datasets/${id}/records/${recordId}`),
    enabled: !!dataset,
  });

  if (loadingDS || loadingRec) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  if (errorDS || errorRec || !dataset || !record) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900">加载失败</h2>
          <p className="mt-2 text-gray-500">
            {errorDS instanceof Error ? errorDS.message : errorRec instanceof Error ? errorRec.message : '记录不存在或无权访问'}
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

  const properties = dataset.schema.properties || {};

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <nav className="flex mb-4 text-sm">
            <Link href="/datasets" className="text-gray-500 hover:text-gray-700">数据集</Link>
            <span className="mx-2 text-gray-400">/</span>
            <Link href={`/datasets/${id}`} className="text-gray-500 hover:text-gray-700">{dataset.name}</Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-gray-900 font-medium">查看记录</span>
          </nav>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">记录详情</h1>
              <p className="mt-1 text-sm text-gray-500">记录 ID: {record.id}</p>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => router.push(`/datasets/${id}`)}
                className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                返回
              </button>
              {can(user, 'update:record') && (
                <button
                  onClick={() => router.push(`/datasets/${id}/${recordId}/edit`)}
                  className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  编辑
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="px-8 py-6 max-w-7xl">
        {record.has_pending_version && (
          <div className="mb-6 rounded-md bg-yellow-50 border border-yellow-200 p-4">
            <p className="text-sm text-yellow-800">此记录有一个待审批的变更</p>
          </div>
        )}

        <div className="bg-white shadow sm:rounded-lg mb-6">
          <div className="px-6 py-6">
            <h3 className="text-lg font-medium text-gray-900 mb-6">记录数据</h3>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-6 sm:grid-cols-2">
              {Object.entries(properties).map(([fieldName, fieldSchema]) => (
                <div key={fieldName}>
                  <dt className="text-sm font-medium text-gray-500">{fieldSchema.title || fieldName}</dt>
                  <dd className="mt-1 text-sm text-gray-900 whitespace-pre-wrap break-words">
                    {formatValue(record.payload[fieldName], fieldSchema)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        <div className="bg-white shadow sm:rounded-lg">
          <div className="px-6 py-6">
            <h3 className="text-lg font-medium text-gray-900 mb-6">元数据</h3>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500">记录 ID</dt>
                <dd className="mt-1 text-sm text-gray-900 font-mono break-all">{record.id}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">当前版本</dt>
                <dd className="mt-1 text-sm text-gray-900">v{record.version}</dd>
              </div>
              {record.status && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">状态</dt>
                  <dd className="mt-1 text-sm text-gray-900">{record.status}</dd>
                </div>
              )}
              {record.created_by && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">创建人</dt>
                  <dd className="mt-1 text-sm text-gray-900">{record.created_by}</dd>
                </div>
              )}
              {record.updated_at && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">更新时间</dt>
                  <dd className="mt-1 text-sm text-gray-900">{new Date(record.updated_at).toLocaleString('zh-CN')}</dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
