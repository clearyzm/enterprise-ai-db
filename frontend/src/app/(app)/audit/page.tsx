'use client';

import { useState, Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

interface AuditLogEntry {
  id: number;
  tenant_id: string | null;
  user_id: string | null;
  user_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, any>;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
}

interface AuditLogsResponse {
  logs: AuditLogEntry[];
  total: number;
}

// ============================================================================
// Action labels (for display)
// ============================================================================

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  login: { label: '登录', color: 'bg-green-100 text-green-800' },
  update_user: { label: '修改用户', color: 'bg-blue-100 text-blue-800' },
  disable_user: { label: '禁用用户', color: 'bg-red-100 text-red-800' },
  update_record: { label: '修改记录', color: 'bg-amber-100 text-amber-800' },
  approve: { label: '审批通过', color: 'bg-emerald-100 text-emerald-800' },
  reject: { label: '审批拒绝', color: 'bg-rose-100 text-rose-800' },
};

const RESOURCE_LABELS: Record<string, string> = {
  user: '用户',
  record: '数据记录',
  approval: '审批',
  audit_log: '审计日志',
};

// ============================================================================
// Main Component
// ============================================================================

export default function AuditPage() {
  const [actionFilter, setActionFilter] = useState('all');
  const [resourceFilter, setResourceFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useQuery<AuditLogsResponse>({
    queryKey: ['audit', actionFilter, resourceFilter, searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (actionFilter !== 'all') params.append('action', actionFilter);
      if (resourceFilter !== 'all') params.append('resource_type', resourceFilter);
      if (searchQuery) params.append('search', searchQuery);
      params.append('limit', '100');
      return api.get<AuditLogsResponse>(`/audit?${params.toString()}`);
    },
  });

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('zh-CN', { hour12: false });
    } catch {
      return iso;
    }
  };

  const getActionBadge = (action: string) => {
    const config = ACTION_LABELS[action] || { label: action, color: 'bg-gray-100 text-gray-800' };
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
        {config.label}
      </span>
    );
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-8">

      {/* Header */}
      <div className="sm:flex sm:items-center">

        <div className="sm:flex-auto">

          <div>

            <div>

              <h1 className="text-2xl font-semibold text-gray-900">
                审计日志
              </h1>

              <p className="mt-2 text-sm text-gray-700">
                租户内所有安全相关操作的不可变记录
              </p>

            </div>

            <button onClick={() => refetch()}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              刷新
            </button>
          </div>

        </div>

      </div>


      {/* Filters */}
      <div className="mt-6">

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">

          <div>

            <label className="block text-sm font-medium text-gray-700 mb-1">
              搜索
            </label>
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="按 action / resource 搜索"
                className="block w-full pl-3 pr-3 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              />
            </div>


            <div>

              <label className="block text-sm font-medium text-gray-700 mb-1">
                动作类型
              </label>
              <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">全部动作</option>
                <option value="login">登录</option>
                <option value="update_user">修改用户</option>
                <option value="disable_user">禁用用户</option>
                <option value="update_record">修改记录</option>
                <option value="approve">审批通过</option>
                <option value="reject">审批拒绝</option>
              </select>
            </div>


            <div>

              <label className="block text-sm font-medium text-gray-700 mb-1">
                资源类型
              </label>
              <select value={resourceFilter} onChange={(e) => setResourceFilter(e.target.value)}
                className="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="all">全部资源</option>
                <option value="user">用户</option>
                <option value="record">数据记录</option>
                <option value="approval">审批</option>
              </select>
            </div>

          </div>

        </div>


      {/* Content */}
      <div className="mt-8">

        {/* Stats summary */}
        {data && (
          <div className="mb-4 text-sm text-gray-600">
            共 {data.total} 条日志记录
            {(actionFilter !== 'all' || resourceFilter !== 'all' || searchQuery) && '（已筛选）'}
          </div>
        )}

        {isLoading && (
          <div className="text-center py-12">

            <div className="inline-block">

              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>

              <p className="mt-2 text-sm text-gray-500">加载中...</p>

            </div>

          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 p-4">

            <p className="text-sm text-red-800">
              {error instanceof Error ? error.message : '加载审计日志失败'}
            </p>

          </div>
        )}

        {!isLoading && !error && data && data.logs.length === 0 && (
          <div className="text-center py-12">

            <p className="text-sm text-gray-500">没有符合条件的审计日志</p>

          </div>
        )}

        {!isLoading && !error && data && data.logs.length > 0 && (
          <div className="overflow-x-auto shadow ring-1 ring-black ring-opacity-5 rounded-lg">

            <table className="min-w-full divide-y divide-gray-300">
              <thead className="bg-gray-50">
                <tr>
                  <th className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900">
                    时间
                  </th>
                  <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                    操作者
                  </th>
                  <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                    动作
                  </th>
                  <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                    资源
                  </th>
                  <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                    资源 ID
                  </th>
                  <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                    详情
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {data.logs.map((log) => {
                  const isExpanded = expandedRow === log.id;
                  return (
                    <Fragment key={log.id}>
                      <tr className="hover:bg-gray-50">
                        <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm text-gray-900">
                          {formatDate(log.created_at)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-900">
                          {log.user_email || '系统'}
                        </td>
                        <td className="whitespace-nowrap px-3 py-4 text-sm">
                          {getActionBadge(log.action)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-900">
                          {RESOURCE_LABELS[log.resource_type] || log.resource_type}
                        </td>
                        <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 font-mono">
                          {log.resource_id ? log.resource_id.slice(0, 8) + '...' : '—'}
                        </td>
                        <td className="whitespace-nowrap px-3 py-4 text-sm">
                          {Object.keys(log.detail || {}).length > 0 ? (
                            <button onClick={() => setExpandedRow(isExpanded ? null : log.id)}
                              className="text-blue-600 hover:text-blue-900 text-xs"
                            >
                              {isExpanded ? '收起' : '查看 JSON'}
                            </button>
                          ) : (
                            <span className="text-gray-400">无详情</span>
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={6} className="px-4 py-4 bg-gray-50">

                            <div className="space-y-2">

                              <p className="text-xs font-semibold text-gray-700">
                                完整 detail（JSON）：
                              </p>

                              <pre className="text-xs bg-white p-3 rounded border border-gray-200 overflow-x-auto">
                                {JSON.stringify(log.detail, null, 2)}
                              </pre>

                              {log.resource_id && (
                                <p className="text-xs text-gray-600">
                                  完整 Resource ID: {log.resource_id}
                                </p>
                              )}
                            </div>

                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>

          </div>
        )}
      </div>

    </div>
  );
}
