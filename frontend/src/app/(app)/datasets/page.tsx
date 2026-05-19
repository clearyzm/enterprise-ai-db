/**
 * Datasets list page with search, filter, and create.
 * 
 * Features:
 * - List all datasets user has access to
 * - Search by name
 * - Filter by status, sensitivity
 * - Create new dataset (if has permission)
 * - Navigate to dataset detail
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageDatasets } from '@/lib/permissions';

// ============================================================================
// Types
// ============================================================================

interface Dataset {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  schema: Record<string, unknown>;
  ui_config: Record<string, unknown>;
  indexes: Array<Record<string, unknown>>;
  owner_dept_id: string | null;
  workflow_id: string | null;
  ai_indexed: boolean;
  sensitivity: string;
  status: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  owner_department?: {
    id: string;
    name: string;
  } | null;
  creator?: {
    id: string;
    display_name: string;
  } | null;
}

interface DatasetsResponse {
  datasets: Dataset[];
  total: number;
}

// ============================================================================
// Component
// ============================================================================

export default function DatasetsPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const canManage = canManageDatasets(user);

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sensitivityFilter, setSensitivityFilter] = useState<string>('all');

  // Fetch datasets
  const { data, isLoading, error } = useQuery<DatasetsResponse>({
    queryKey: ['datasets', searchQuery, statusFilter, sensitivityFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (sensitivityFilter !== 'all') params.append('sensitivity', sensitivityFilter);

      const queryString = params.toString();
      const endpoint = `/datasets${queryString ? `?${queryString}` : ''}`;
      
      return api.get<DatasetsResponse>(endpoint);
    },
  });

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
  };

  const handleCreate = () => {
    router.push('/datasets/new');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">数据集</h1>
              <p className="mt-1 text-sm text-gray-500">管理和浏览所有数据集</p>
            </div>
            {canManage && (
              <button
                onClick={handleCreate}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                创建数据集
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-4">
          <div className="flex items-center space-x-4">
            {/* Search */}
            <div className="flex-1 max-w-lg">
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <input
                  type="text"
                  placeholder="搜索数据集名称..."
                  value={searchQuery}
                  onChange={handleSearch}
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                />
              </div>
            </div>

            {/* Status Filter */}
            <div>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">所有状态</option>
                <option value="active">活跃</option>
                <option value="archived">已归档</option>
              </select>
            </div>

            {/* Sensitivity Filter */}
            <div>
              <select
                value={sensitivityFilter}
                onChange={(e) => setSensitivityFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">所有敏感度</option>
                <option value="public">公开</option>
                <option value="internal">内部</option>
                <option value="confidential">机密</option>
                <option value="secret">绝密</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-8 py-6">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex flex-col items-center space-y-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p className="text-gray-500">加载中...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 p-4">
            <p className="text-sm font-medium text-red-800">
              {error instanceof Error ? error.message : '加载数据集失败'}
            </p>
          </div>
        )}

        {!isLoading && !error && data && data.datasets.length === 0 && (
          <EmptyState 
            searchQuery={searchQuery}
            statusFilter={statusFilter}
            sensitivityFilter={sensitivityFilter}
            canManage={canManage}
            onCreateClick={handleCreate}
          />
        )}

        {!isLoading && !error && data && data.datasets.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {data.datasets.map((dataset) => (
                <DatasetCard key={dataset.id} dataset={dataset} />
              ))}
            </div>
            <div className="mt-6 text-sm text-gray-500">共 {data.total} 个数据集</div>
          </>
        )}
      </div>
    </div>
  );
}

// Empty State Component
function EmptyState({ searchQuery, statusFilter, sensitivityFilter, canManage, onCreateClick }: {
  searchQuery: string;
  statusFilter: string;
  sensitivityFilter: string;
  canManage: boolean;
  onCreateClick: () => void;
}) {
  const hasFilters = searchQuery || statusFilter !== 'all' || sensitivityFilter !== 'all';
  
  return (
    <div className="text-center py-12">
      <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
      </svg>
      <h3 className="mt-2 text-sm font-medium text-gray-900">暂无数据集</h3>
      <p className="mt-1 text-sm text-gray-500">
        {hasFilters ? '没有找到符合条件的数据集' : '开始创建您的第一个数据集'}
      </p>
      {canManage && !hasFilters && (
        <div className="mt-6">
          <button onClick={onCreateClick} className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">
            <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            创建数据集
          </button>
        </div>
      )}
    </div>
  );
}

// Dataset Card Component
function DatasetCard({ dataset }: { dataset: Dataset }) {
  const sensitivityColors: Record<string, string> = {
    public: 'bg-green-100 text-green-800',
    internal: 'bg-blue-100 text-blue-800',
    confidential: 'bg-yellow-100 text-yellow-800',
    secret: 'bg-red-100 text-red-800',
  };

  const sensitivityLabels: Record<string, string> = {
    public: '公开',
    internal: '内部',
    confidential: '机密',
    secret: '绝密',
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    archived: 'bg-gray-100 text-gray-800',
  };

  const statusLabels: Record<string, string> = {
    active: '活跃',
    archived: '已归档',
  };

  return (
    <Link
      href={`/datasets/${dataset.id}`}
      className="block bg-white rounded-lg border border-gray-200 hover:border-blue-500 hover:shadow-md transition-all"
    >
      <div className="p-6">
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-semibold text-gray-900 truncate">{dataset.name}</h3>
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ml-2 ${sensitivityColors[dataset.sensitivity] || 'bg-gray-100 text-gray-800'}`}>
            {sensitivityLabels[dataset.sensitivity] || dataset.sensitivity}
          </span>
        </div>

        <p className="mt-2 text-sm text-gray-500 line-clamp-2">
          {dataset.description || '暂无描述'}
        </p>

        <div className="mt-4 flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center space-x-4">
            <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${statusColors[dataset.status] || 'bg-gray-100 text-gray-800'}`}>
              {statusLabels[dataset.status] || dataset.status}
            </span>
            {dataset.ai_indexed && (
              <span className="inline-flex items-center text-purple-600">
                <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                AI
              </span>
            )}
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
          <span>{dataset.owner_department?.name || '无部门'}</span>
          <span>{new Date(dataset.created_at).toLocaleDateString('zh-CN')}</span>
        </div>
      </div>
    </Link>
  );
}
