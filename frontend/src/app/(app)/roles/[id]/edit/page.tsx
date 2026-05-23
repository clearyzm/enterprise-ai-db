'use client';

import { use, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

interface RoleDetail {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
}

interface UpdateRolePayload {
  name?: string;
  description?: string;
}

export default function EditRolePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: role, isLoading, error: loadError } = useQuery<RoleDetail>({
    queryKey: ['role', id],
    queryFn: () => api.get<RoleDetail>(`/roles/${id}`),
  });

  useEffect(() => {
    if (role) {
      setName(role.name);
      setDescription(role.description || '');
    }
  }, [role]);

  const updateMutation = useMutation({
    mutationFn: (payload: UpdateRolePayload) =>
      api.patch<RoleDetail>(`/roles/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['role', id] });
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      router.push(`/roles/${id}`);
    },
    onError: (err) => {
      setSubmitError(err instanceof Error ? err.message : '保存失败');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const payload: UpdateRolePayload = {};
    if (role) {
      if (name !== role.name && !role.is_system) payload.name = name;
      if (description !== (role.description || '')) payload.description = description;
    }

    if (Object.keys(payload).length === 0) {
      router.push(`/roles/${id}`);
      return;
    }

    updateMutation.mutate(payload);
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

  if (loadError) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <div className="rounded-md bg-red-50 p-4">
            <p className="text-sm font-medium text-red-800">
              {loadError instanceof Error ? loadError.message : '加载角色信息失败'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!role) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-3 max-w-7xl mx-auto">
          <nav className="text-sm text-gray-500">
            <Link href="/roles" className="hover:text-gray-700">角色管理</Link>
            <span className="mx-2">/</span>
            <Link href={`/roles/${id}`} className="hover:text-gray-700">{role.name}</Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900">编辑</span>
          </nav>
        </div>
      </div>

      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6 max-w-7xl mx-auto">
          <h1 className="text-2xl font-bold text-gray-900">编辑角色</h1>
          <p className="mt-1 text-sm text-gray-500">{role.name}</p>
        </div>
      </div>

      <div className="px-8 py-6 max-w-3xl mx-auto">
        <form onSubmit={handleSubmit} className="bg-white shadow rounded-lg p-6 space-y-6">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700">
              角色名
            </label>
            <input
              type="text"
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={role.is_system}
              className={`mt-1 block w-full rounded-md border px-3 py-2 shadow-sm sm:text-sm ${
                role.is_system
                  ? 'border-gray-300 bg-gray-50 text-gray-500'
                  : 'border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500'
              }`}
            />
            {role.is_system && (
              <p className="mt-1 text-xs text-gray-400">系统角色名称不可修改</p>
            )}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700">
              描述
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="请描述该角色的职责与权限范围"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            />
          </div>

          {submitError && (
            <div className="rounded-md bg-red-50 p-4">
              <p className="text-sm font-medium text-red-800">{submitError}</p>
            </div>
          )}

          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={() => router.push(`/roles/${id}`)}
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
