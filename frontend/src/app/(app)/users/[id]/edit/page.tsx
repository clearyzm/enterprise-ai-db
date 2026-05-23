'use client';

import { use, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

interface UserDetail {
  id: string;
  email: string;
  display_name: string;
  status: string;
  is_tenant_admin: boolean;
}

interface UpdateUserPayload {
  display_name?: string;
  status?: string;
  is_tenant_admin?: boolean;
}

// ============================================================================
// Main Component
// ============================================================================

export default function EditUserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  // Form state
  const [displayName, setDisplayName] = useState('');
  const [status, setStatus] = useState('active');
  const [isTenantAdmin, setIsTenantAdmin] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Fetch current user data
  const { data: user, isLoading, error: loadError } = useQuery<UserDetail>({
    queryKey: ['user', id],
    queryFn: () => api.get<UserDetail>(`/users/${id}`),
  });

  // Initialize form when data loads
  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name || '');
      setStatus(user.status);
      setIsTenantAdmin(user.is_tenant_admin);
    }
  }, [user]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (payload: UpdateUserPayload) =>
      api.patch<UserDetail>(`/users/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', id] });
      queryClient.invalidateQueries({ queryKey: ['users'] });
      router.push(`/users/${id}`);
    },
    onError: (err) => {
      setSubmitError(err instanceof Error ? err.message : '保存失败');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const payload: UpdateUserPayload = {};
    if (user) {
      if (displayName !== user.display_name) payload.display_name = displayName;
      if (status !== user.status) payload.status = status;
      if (isTenantAdmin !== user.is_tenant_admin) payload.is_tenant_admin = isTenantAdmin;
    }

    if (Object.keys(payload).length === 0) {
      // No changes, just navigate back
      router.push(`/users/${id}`);
      return;
    }

    updateMutation.mutate(payload);
  };

  // Loading
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

  if (loadError) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="rounded-md bg-red-50 p-4">
            <p className="text-sm font-medium text-red-800">
              {loadError instanceof Error ? loadError.message : '加载用户信息失败'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-3 max-w-7xl mx-auto">
          <nav className="text-sm text-gray-500">
            <Link href="/users" className="hover:text-gray-700">用户管理</Link>
            <span className="mx-2">/</span>
            <Link href={`/users/${id}`} className="hover:text-gray-700">{user.email}</Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900">编辑</span>
          </nav>
        </div>
      </div>

      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <h1 className="text-2xl font-bold text-gray-900">编辑用户</h1>
          <p className="mt-1 text-sm text-gray-500">{user.email}</p>
        </div>
      </div>

      {/* Form */}
      <div className="px-8 py-6 max-w-3xl mx-auto">
        <form onSubmit={handleSubmit} className="bg-white shadow rounded-lg p-6 space-y-6">
          {/* Email (readonly) */}
          <div>
            <label className="block text-sm font-medium text-gray-700">邮箱</label>
            <input
              type="email"
              value={user.email}
              disabled
              className="mt-1 block w-full rounded-md border-gray-300 bg-gray-50 text-gray-500 shadow-sm sm:text-sm"
            />
            <p className="mt-1 text-xs text-gray-400">邮箱不可修改</p>
          </div>

          {/* Display Name */}
          <div>
            <label htmlFor="display_name" className="block text-sm font-medium text-gray-700">
              姓名
            </label>
            <input
              type="text"
              id="display_name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="请输入显示姓名"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>

          {/* Status */}
          <div>
            <label htmlFor="status" className="block text-sm font-medium text-gray-700">
              状态
            </label>
            <select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            >
              <option value="active">活跃</option>
              <option value="disabled">已禁用</option>
            </select>
            <p className="mt-1 text-xs text-gray-400">
              已禁用的用户无法登录，但其历史数据保留
            </p>
          </div>

          {/* Tenant Admin */}
          <div>
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isTenantAdmin}
                onChange={(e) => setIsTenantAdmin(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="ml-2 text-sm font-medium text-gray-700">租户管理员</span>
            </label>
            <p className="mt-1 text-xs text-gray-400 ml-6">
              租户管理员拥有完整权限，可以管理本租户所有资源
            </p>
          </div>

          {/* Submit error */}
          {submitError && (
            <div className="rounded-md bg-red-50 p-4">
              <p className="text-sm font-medium text-red-800">{submitError}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={() => router.push(`/users/${id}`)}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300"
            >
              {updateMutation.isPending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
