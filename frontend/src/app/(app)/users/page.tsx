'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageUsers } from '@/lib/permissions';

// ============================================================================
// Types
// ============================================================================

interface UserListItem {
  id: string;
  email: string;
  display_name: string;
  status: string;
  is_tenant_admin: boolean;
  roles: Array<{
    role_id: string;
    role_name: string;
    scope: Record<string, unknown>;
  }>;
  departments: Array<{
    department_id: string;
    department_name: string;
    is_primary: boolean;
  }>;
  last_login_at: string | null;
  created_at: string;
}

interface UsersResponse {
  users: UserListItem[];
  total: number;
}

interface Department {
  id: string;
  name: string;
  parent_id: string | null;
}

interface DepartmentsResponse {
  departments: Department[];
  total: number;
}

// ============================================================================
// Main Component
// ============================================================================

export default function UsersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const canManage = canManageUsers(user);

  const [searchQuery, setSearchQuery] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Fetch departments for filter dropdown
  const { data: deptData } = useQuery<DepartmentsResponse>({
    queryKey: ['departments'],
    queryFn: () => api.get<DepartmentsResponse>('/departments'),
  });

  // Fetch users list
  const { data, isLoading, error } = useQuery<UsersResponse>({
    queryKey: ['users', searchQuery, departmentFilter, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (departmentFilter !== 'all') params.append('department_id', departmentFilter);
      if (statusFilter !== 'all') params.append('status', statusFilter);
      const endpoint = params.toString() ? `/users?${params.toString()}` : '/users';
      return api.get<UsersResponse>(endpoint);
    },
  });

  // Disable user mutation
  const disableMutation = useMutation({
    mutationFn: (userId: string) => api.delete<void>(`/users/${userId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });

  const handleDisable = (userId: string, email: string) => {
    if (confirm(`确认禁用用户 ${email}？此操作可通过编辑用户重新启用。`)) {
      disableMutation.mutate(userId);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">用户管理</h1>
              <p className="mt-1 text-sm text-gray-500">管理租户内的用户、角色与部门归属</p>
            </div>
            {canManage && (
              <button
                onClick={() => alert('邀请用户功能开发中')}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                邀请用户
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-4 max-w-7xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Search */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">搜索</label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="邮箱或姓名"
                className="block w-full pl-3 pr-3 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              />
            </div>

            {/* Department Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">部门</label>
              <select
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">全部部门</option>
                {deptData?.departments?.map((dept) => (
                  <option key={dept.id} value={dept.id}>{dept.name}</option>
                ))}
              </select>
            </div>

            {/* Status Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">状态</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">全部状态</option>
                <option value="active">活跃</option>
                <option value="disabled">已禁用</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-8 py-6 max-w-7xl mx-auto">
        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex flex-col items-center space-y-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p className="text-gray-500">加载中...</p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-md bg-red-50 p-4">
            <p className="text-sm font-medium text-red-800">
              {error instanceof Error ? error.message : '加载用户列表失败'}
            </p>
          </div>
        )}

        {/* Empty */}
        {!isLoading && !error && data && data.users.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500">没有符合条件的用户</p>
          </div>
        )}

        {/* User Table */}
        {!isLoading && !error && data && data.users.length > 0 && (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">邮箱</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">姓名</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">角色</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">部门</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">最后登录</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {data.users.map((u) => (
                  <UserRow
                    key={u.id}
                    user={u}
                    canManage={canManage}
                    onDisable={() => handleDisable(u.id, u.email)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// User Row Component
// ============================================================================

function UserRow({ user, canManage, onDisable }: {
  user: UserListItem;
  canManage: boolean;
  onDisable: () => void;
}) {
  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    disabled: 'bg-gray-100 text-gray-600',
  };

  const statusLabels: Record<string, string> = {
    active: '活跃',
    disabled: '已禁用',
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('zh-CN', { hour12: false });
    } catch {
      return iso;
    }
  };

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
        {user.email}
        {user.is_tenant_admin && (
          <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
            管理员
          </span>
        )}
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{user.display_name || '—'}</td>
      <td className="px-6 py-4 text-sm text-gray-900">
        <div className="flex flex-wrap gap-1">
          {user.roles.length === 0 ? (
            <span className="text-gray-400">—</span>
          ) : (
            user.roles.map((r) => (
              <span
                key={r.role_id}
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
              >
                {r.role_name}
              </span>
            ))
          )}
        </div>
      </td>
      <td className="px-6 py-4 text-sm text-gray-900">
        <div className="flex flex-wrap gap-1">
          {user.departments.length === 0 ? (
            <span className="text-gray-400">—</span>
          ) : (
            user.departments.map((d) => (
              <span
                key={d.department_id}
                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                  d.is_primary ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-800'
                }`}
              >
                {d.department_name}
                {d.is_primary && <span className="ml-1">★</span>}
              </span>
            ))
          )}
        </div>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <span
          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
            statusColors[user.status] || 'bg-gray-100 text-gray-800'
          }`}
        >
          {statusLabels[user.status] || user.status}
        </span>
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{formatDate(user.last_login_at)}</td>
      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-3">
        <Link href={`/users/${user.id}`} className="text-blue-600 hover:text-blue-900">
          查看
        </Link>
        {canManage && (
          <>
            <Link href={`/users/${user.id}/edit`} className="text-blue-600 hover:text-blue-900">
              编辑
            </Link>
            {user.status === 'active' && (
              <button onClick={onDisable} className="text-red-600 hover:text-red-900">
                禁用
              </button>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
