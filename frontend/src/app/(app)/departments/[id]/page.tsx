'use client';

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

interface DepartmentDetail {
  id: string;
  name: string;
  code: string | null;
  parent_id: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

interface DepartmentsResponse {
  departments: DepartmentDetail[];
  total: number;
}

export default function DepartmentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const { data: dept, isLoading, error } = useQuery<DepartmentDetail>({
    queryKey: ['department', id],
    queryFn: () => api.get<DepartmentDetail>(`/departments/${id}`),
  });

  // Fetch all departments for parent name lookup
  const { data: allDeptsData } = useQuery<DepartmentsResponse>({
    queryKey: ['departments'],
    queryFn: () => api.get<DepartmentsResponse>('/departments'),
  });

  const parentDept = dept?.parent_id
    ? allDeptsData?.departments.find((d) => d.id === dept.parent_id)
    : null;

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('zh-CN', { hour12: false });
    } catch {
      return iso;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="rounded-md bg-red-50 p-4">
            <p className="text-sm font-medium text-red-800">
              {error instanceof Error ? error.message : '加载部门详情失败'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!dept) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-3 max-w-7xl mx-auto">
          <nav className="text-sm text-gray-500">
            <Link href="/departments" className="hover:text-gray-700">部门管理</Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900">{dept.name}</span>
          </nav>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900">{dept.name}</h1>
            {dept.code && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                {dept.code}
              </span>
            )}
          </div>
          <button
            onClick={() => router.push('/departments')}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
          >
            返回
          </button>
        </div>
      </div>

      <div className="px-8 py-6 max-w-7xl mx-auto">
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">基本信息</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
            <div>
              <dt className="text-sm font-medium text-gray-500">部门名</dt>
              <dd className="mt-1 text-sm text-gray-900">{dept.name}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">编码</dt>
              <dd className="mt-1 text-sm text-gray-900">{dept.code || '—'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">上级部门</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {parentDept ? (
                  <Link href={`/departments/${parentDept.id}`} className="text-blue-600 hover:text-blue-900">
                    {parentDept.name}
                  </Link>
                ) : (
                  <span className="text-gray-400">顶级部门（无上级）</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">部门 ID</dt>
              <dd className="mt-1 text-xs text-gray-600 font-mono">{dept.id}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">创建时间</dt>
              <dd className="mt-1 text-sm text-gray-900">{formatDate(dept.created_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">更新时间</dt>
              <dd className="mt-1 text-sm text-gray-900">{formatDate(dept.updated_at)}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
