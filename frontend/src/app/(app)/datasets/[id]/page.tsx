/**
 * Dataset detail page with records list.
 * 
 * ⚠️ SIMPLIFIED IMPLEMENTATION (Phase 9 v1):
 * - ❌ Does NOT implement advanced filtering (filter by field values)
 * - ❌ Does NOT implement sorting (click table header to sort)
 * - ❌ Does NOT implement bulk operations (multi-select + bulk delete)
 * - ❌ Does NOT implement export (CSV/Excel)
 * - ✅ Only implements: search + pagination + basic table
 * 
 * TODO (Phase 10+):
 * - Add column sorting (click header to toggle asc/desc)
 * - Add advanced filters (filter by specific field values)
 * - Add bulk selection and operations
 * - Add export to CSV/Excel
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canCreateRecords } from '@/lib/permissions';

interface Dataset {
  id: string;
  name: string;
  description: string | null;
  schema: Record<string, unknown>;
  sensitivity: string;
  status: string;
  ai_indexed: boolean;
}

interface Record {
  id: string;
  payload: Record<string, unknown>;
  version: number;
  updated_at: string;
}

interface RecordsResponse {
  items: Record[];
  total: number;
  page: number;
  total_pages: number;
}

export default function DatasetDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const canCreate = canCreateRecords(user);
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  const { data: dataset, isLoading: loadingDS, error: errorDS } = useQuery<Dataset>({
    queryKey: ['dataset', params.id],
    queryFn: () => api.get<Dataset>(`/datasets/${params.id}`),
  });

  const { data: recordsData, isLoading: loadingRec, error: errorRec } = useQuery<RecordsResponse>({
    queryKey: ['records', params.id, searchQuery, page],
    queryFn: async () => {
      const q = new URLSearchParams({ page: page.toString(), page_size: '20' });
      if (searchQuery) q.append('search', searchQuery);
      return api.get<RecordsResponse>(`/datasets/${params.id}/records?${q}`);
    },
    enabled: !!dataset,
  });

  if (loadingDS) return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>;
  if (errorDS || !dataset) return <div className="min-h-screen flex items-center justify-center"><div className="text-center"><h2 className="text-2xl font-bold text-gray-900">加载失败</h2><button onClick={() => router.push('/datasets')} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md">返回</button></div></div>;

  const properties = (dataset.schema as { properties?: Record<string, unknown> }).properties || {};
  const fields = Object.keys(properties).slice(0, 4);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <nav className="flex mb-4 text-sm">
            <Link href="/datasets" className="text-gray-500 hover:text-gray-700">数据集</Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-gray-900 font-medium">{dataset.name}</span>
          </nav>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-gray-900">{dataset.name}</h1>
              {dataset.description && <p className="mt-1 text-sm text-gray-500">{dataset.description}</p>}
              <div className="mt-3 flex items-center space-x-4 text-xs">
                <span className={`px-2.5 py-0.5 rounded-full font-medium ${getSensColor(dataset.sensitivity)}`}>{getSensLabel(dataset.sensitivity)}</span>
                <span className={`px-2.5 py-0.5 rounded-full font-medium ${getStatColor(dataset.status)}`}>{getStatLabel(dataset.status)}</span>
                {dataset.ai_indexed && <span className="text-purple-600">AI 索引</span>}
              </div>
            </div>
            {canCreate && <button onClick={() => router.push(`/datasets/${params.id}/new`)} className="px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">新增记录</button>}
          </div>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200 px-8 py-4">
        <input type="text" placeholder="搜索记录..." value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }} className="w-full max-w-lg px-3 py-2 border border-gray-300 rounded-md focus:ring-1 focus:ring-blue-500 focus:border-blue-500 text-sm" />
      </div>

      <div className="px-8 py-6">
        {loadingRec && <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>}
        {errorRec && <div className="rounded-md bg-red-50 p-4"><p className="text-sm text-red-800">{errorRec instanceof Error ? errorRec.message : '加载失败'}</p></div>}
        {!loadingRec && !errorRec && recordsData && recordsData.items.length === 0 && (
          <div className="text-center py-12">
            <h3 className="text-sm font-medium text-gray-900">暂无记录</h3>
            <p className="mt-1 text-sm text-gray-500">{searchQuery ? '没有找到符合条件的记录' : '开始创建第一条记录'}</p>
            {canCreate && !searchQuery && <button onClick={() => router.push(`/datasets/${params.id}/new`)} className="mt-6 px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">新增记录</button>}
          </div>
        )}
        {!loadingRec && !errorRec && recordsData && recordsData.items.length > 0 && (
          <>
            <div className="bg-white shadow overflow-hidden sm:rounded-lg">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    {fields.map((f) => <th key={f} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{f}</th>)}
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">版本</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">更新时间</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">操作</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {recordsData.items.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      {fields.map((f) => <td key={f} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{fmt(r.payload[f])}</td>)}
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">v{r.version}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(r.updated_at).toLocaleString('zh-CN')}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                        <Link href={`/datasets/${params.id}/${r.id}`} className="text-blue-600 hover:text-blue-900 mr-4">查看</Link>
                        <Link href={`/datasets/${params.id}/${r.id}/edit`} className="text-blue-600 hover:text-blue-900">编辑</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {recordsData.total_pages > 1 && (
              <div className="mt-6 flex items-center justify-between">
                <div className="text-sm text-gray-500">共 {recordsData.total} 条，第 {recordsData.page} / {recordsData.total_pages} 页</div>
                <div className="flex space-x-2">
                  <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="px-3 py-1 border rounded-md text-sm bg-white hover:bg-gray-50 disabled:opacity-50">上一页</button>
                  <button onClick={() => setPage(Math.min(recordsData.total_pages, page + 1))} disabled={page === recordsData.total_pages} className="px-3 py-1 border rounded-md text-sm bg-white hover:bg-gray-50 disabled:opacity-50">下一页</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function getSensColor(s: string): string {
  const c: Record<string, string> = { public: 'bg-green-100 text-green-800', internal: 'bg-blue-100 text-blue-800', confidential: 'bg-yellow-100 text-yellow-800', secret: 'bg-red-100 text-red-800' };
  return c[s] || 'bg-gray-100 text-gray-800';
}

function getSensLabel(s: string): string {
  const l: Record<string, string> = { public: '公开', internal: '内部', confidential: '机密', secret: '绝密' };
  return l[s] || s;
}

function getStatColor(s: string): string {
  return s === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800';
}

function getStatLabel(s: string): string {
  return s === 'active' ? '活跃' : '已归档';
}
