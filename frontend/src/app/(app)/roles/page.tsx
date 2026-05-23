'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageUsers } from '@/lib/permissions';

interface RoleListItem {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

interface RolesResponse {
  roles: RoleListItem[];
  total: number;
}

export default function RolesPage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const canManage = canManageUsers(user);

  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, error } = useQuery<RolesResponse>({
    queryKey: ['roles', searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      const endpoint = params.toString() ? `/roles?${params.toString()}` : '/roles';
      return api.get<RolesResponse>(endpoint);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (roleId: string) => api.delete<void>(`/roles/${roleId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] });
    },
    onError: (err) => {
      alert(err instanceof Error ? err.message : '删除失败');
    },
  });

  const handleDelete = (roleId: string, name: string, isSystem: boolean) => {
    if (isSystem) {
      alert(`角色 "${name}" 是系统角色，不能删除`);
      return;
    }
    if (confirm(`确认删除角色 "${name}"？此操作不可撤销。`)) {
      deleteMutation.mutate(roleId);
    }
  };

  // Client-side search filter (in case backend doesn't support search)
  const filteredRoles = data?.roles.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return r.name.toLowerCase().includes(q) || (r.description?.toLowerCase().includes(q) ?? false);
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">角色管理</h1>
              <p className="mt-1 text-sm text-gray-500">管理租户内的角色与权限配置</p>
            </div>
            {canManage && (
              <button
                onClick={() => alert('新建角色功能开发中')}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700"
              >
                新建角色
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
              placeholder="角色名称或描述"
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
              {error instanceof Error ? error.message : '加载角色列表失败'}
            </p>
          </div>
        )}

        {!isLoading && !error && filteredRoles && filteredRoles.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500">没有符合条件的角色</p>
          </div>
        )}

        {!isLoading && !error && filteredRoles && filteredRoles.length > 0 && (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">角色名</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">描述</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">类型</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">创建时间</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredRoles.map((role) => (
                  <tr key={role.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-sm font-medium bg-blue-100 text-blue-800">
                        {role.name}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-700">{role.description || '—'}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {role.is_system ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                          系统角色
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                          自定义
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(role.created_at).toLocaleString('zh-CN', { hour12: false })}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-3">
                      <Link href={`/roles/${role.id}`} className="text-blue-600 hover:text-blue-900">查看</Link>
                      {canManage && (
                        <>
                          <Link href={`/roles/${role.id}/edit`} className="text-blue-600 hover:text-blue-900">编辑</Link>
                          {!role.is_system && (
                            <button
                              onClick={() => handleDelete(role.id, role.name, role.is_system)}
                              className="text-red-600 hover:text-red-900"
                            >
                              删除
                            </button>
                          )}
                        </>
                      )}
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
