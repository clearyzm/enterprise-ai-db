'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageUsers } from '@/lib/permissions';

interface DepartmentItem {
  id: string;
  name: string;
  code: string | null;
  parent_id: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

interface DepartmentsResponse {
  departments: DepartmentItem[];
  total: number;
}

export default function DepartmentsPage() {
  const user = useAuthStore((state) => state.user);
  const canManage = canManageUsers(user);

  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, error } = useQuery<DepartmentsResponse>({
    queryKey: ['departments'],
    queryFn: () => api.get<DepartmentsResponse>('/departments'),
  });

  const filteredDepartments = data?.departments.filter((d) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return d.name.toLowerCase().includes(q) || (d.code?.toLowerCase().includes(q) ?? false);
  });

  // Build a map for parent name lookup
  const departmentMap = new Map<string, string>();
  data?.departments.forEach((d) => departmentMap.set(d.id, d.name));

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">部门管理</h1>
              <p className="mt-1 text-sm text-gray-500">管理租户内的部门组织结构</p>
            </div>
            {canManage && (
              <button
                onClick={() => alert('新建部门功能开发中')}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700"
              >
                新建部门
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-4 max-w-7xl mx-auto">
          <div className="max-w-md">
            <label className="block text-sm font-medium text-gray-700 mb-1">搜索</label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="部门名称或编码"
              className="block w-full pl-3 pr-3 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
            />
          </div>
        </div>
      </div>

      <div className="px-8 py-6 max-w-7xl mx-auto">
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
              {error instanceof Error ? error.message : '加载部门列表失败'}
            </p>
          </div>
        )}

        {!isLoading && !error && filteredDepartments && filteredDepartments.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500">没有符合条件的部门</p>
          </div>
        )}

        {!isLoading && !error && filteredDepartments && filteredDepartments.length > 0 && (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">部门名</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">编码</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">上级部门</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">创建时间</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredDepartments.map((dept) => (
                  <tr key={dept.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-sm font-medium bg-indigo-100 text-indigo-800">
                        {dept.name}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {dept.code || '—'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {dept.parent_id ? (departmentMap.get(dept.parent_id) || '—') : <span className="text-gray-400">顶级部门</span>}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(dept.created_at).toLocaleString('zh-CN', { hour12: false })}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <Link href={`/departments/${dept.id}`} className="text-blue-600 hover:text-blue-900">查看</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
