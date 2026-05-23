'use client';

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import { canManageUsers } from '@/lib/permissions';

// ============================================================================
// Types
// ============================================================================

interface UserDetail {
  id: string;
  email: string;
  display_name: string;
  status: string;
  is_tenant_admin: boolean;
  tenant_id: string;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
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
}

// ============================================================================
// Main Component
// ============================================================================

export default function UserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const currentUser = useAuthStore((state) => state.user);
  const canManage = canManageUsers(currentUser);

  const { data: user, isLoading, error } = useQuery<UserDetail>({
    queryKey: ['user', id],
    queryFn: () => api.get<UserDetail>(`/users/${id}`),
  });

  const formatDate = (iso: string | null) => {
    if (!iso) return '—';
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
              {error instanceof Error ? error.message : '加载用户详情失败'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    disabled: 'bg-gray-100 text-gray-600',
  };

  const statusLabels: Record<string, string> = {
    active: '活跃',
    disabled: '已禁用',
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-3 max-w-7xl mx-auto">
          <nav className="text-sm text-gray-500">
            <Link href="/users" className="hover:text-gray-700">用户管理</Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900">{user.email}</span>
          </nav>
        </div>
      </div>

      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900">{user.email}</h1>
            {user.is_tenant_admin && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                管理员
              </span>
            )}
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[user.status] || 'bg-gray-100 text-gray-800'}`}>
              {statusLabels[user.status] || user.status}
            </span>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => router.push('/users')}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              返回
            </button>
            {canManage && (
              <Link
                href={`/users/${id}/edit`}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700"
              >
                编辑
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-8 py-6 max-w-7xl mx-auto space-y-6">
        {/* Basic Info */}
        <Section title="基本信息">
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
            <Field label="邮箱" value={user.email} />
            <Field label="姓名" value={user.display_name || '—'} />
            <Field label="租户管理员" value={user.is_tenant_admin ? '是' : '否'} />
            <Field label="状态" value={statusLabels[user.status] || user.status} />
            <Field label="最后登录" value={formatDate(user.last_login_at)} />
            <Field label="创建时间" value={formatDate(user.created_at)} />
          </dl>
        </Section>

        {/* Departments */}
        <Section
          title="部门归属"
          action={canManage ? (
            <button
              onClick={() => alert('部门归属管理功能开发中')}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              添加部门
            </button>
          ) : null}
        >
          {user.departments.length === 0 ? (
            <p className="text-sm text-gray-500">未分配部门</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {user.departments.map((d) => (
                <span
                  key={d.department_id}
                  className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                    d.is_primary ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {d.department_name}
                  {d.is_primary && <span className="ml-1">★</span>}
                </span>
              ))}
            </div>
          )}
        </Section>

        {/* Roles */}
        <Section
          title="角色"
          action={canManage ? (
            <button
              onClick={() => alert('角色管理功能开发中')}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              添加角色
            </button>
          ) : null}
        >
          {user.roles.length === 0 ? (
            <p className="text-sm text-gray-500">未分配角色</p>
          ) : (
            <div className="space-y-2">
              {user.roles.map((r) => (
                <div
                  key={r.role_id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-md"
                >
                  <div>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 mr-2">
                      {r.role_name}
                    </span>
                    {Object.keys(r.scope).length > 0 && (
                      <span className="text-xs text-gray-500">
                        scope: {JSON.stringify(r.scope)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

// ============================================================================
// Section Component
// ============================================================================

function Section({ title, action, children }: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

// ============================================================================
// Field Component
// ============================================================================

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm font-medium text-gray-500">{label}</dt>
      <dd className="mt-1 text-sm text-gray-900">{value}</dd>
    </div>
  );
}
