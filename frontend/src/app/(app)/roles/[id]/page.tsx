'use client';

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageUsers } from '@/lib/permissions';

interface Permission {
  id: string;
  action: string;
  resource_type: string;
  description: string | null;
}

interface RoleDetail {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;
  permissions: Permission[];
}

export default function RoleDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const currentUser = useAuthStore((state) => state.user);
  const canManage = canManageUsers(currentUser);

  const { data: role, isLoading, error } = useQuery<RoleDetail>({
    queryKey: ['role', id],
    queryFn: () => api.get<RoleDetail>(`/roles/${id}`),
  });

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
              {error instanceof Error ? error.message : '加载角色详情失败'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!role) return null;

  // Group permissions by resource_type
  const groupedPermissions: Record<string, Permission[]> = {};
  for (const p of role.permissions) {
    if (!groupedPermissions[p.resource_type]) groupedPermissions[p.resource_type] = [];
    groupedPermissions[p.resource_type].push(p);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-3 max-w-7xl mx-auto">
          <nav className="text-sm text-gray-500">
            <Link href="/roles" className="hover:text-gray-700">角色管理</Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900">{role.name}</span>
          </nav>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900">{role.name}</h1>
            {role.is_system ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                系统角色
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                自定义
              </span>
            )}
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => router.push('/roles')}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              返回
            </button>
            {canManage && (
              <Link
                href={`/roles/${id}/edit`}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700"
              >
                编辑
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="px-8 py-6 max-w-7xl mx-auto space-y-6">
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">基本信息</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
            <div>
              <dt className="text-sm font-medium text-gray-500">角色名</dt>
              <dd className="mt-1 text-sm text-gray-900">{role.name}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">类型</dt>
              <dd className="mt-1 text-sm text-gray-900">{role.is_system ? '系统角色' : '自定义'}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-sm font-medium text-gray-500">描述</dt>
              <dd className="mt-1 text-sm text-gray-900">{role.description || '—'}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">创建时间</dt>
              <dd className="mt-1 text-sm text-gray-900">{formatDate(role.created_at)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">更新时间</dt>
              <dd className="mt-1 text-sm text-gray-900">{formatDate(role.updated_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">权限列表（{role.permissions.length}）</h2>
          </div>
          {role.permissions.length === 0 ? (
            <p className="text-sm text-gray-500">该角色没有任何权限</p>
          ) : (
            <div className="space-y-4">
              {Object.entries(groupedPermissions).map(([resourceType, perms]) => (
                <div key={resourceType}>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">{resourceType}</h3>
                  <div className="flex flex-wrap gap-2">
                    {perms.map((p) => (
                      <span
                        key={p.id}
                        title={p.description || ''}
                        className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-blue-100 text-blue-800"
                      >
                        {p.action}:{p.resource_type}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
