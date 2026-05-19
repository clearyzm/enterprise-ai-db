/**
 * Approvals page with Inbox/Outbox tabs.
 * 
 * Features:
 * - Inbox: Pending approvals awaiting my action
 * - Outbox: Versions I submitted (all states)
 * - Click to navigate to approval detail page
 * - Real-time updates via WebSocket (Phase 10)
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

interface ApprovalInboxItem {
  version_id: string;
  record_id: string | null;
  dataset_id: string;
  dataset_name: string;
  op: 'insert' | 'update' | 'delete';
  current_step: number;
  step_name: string;
  workflow_name: string;
  proposed_by_id: string;
  proposed_by_email: string | null;
  proposed_by_name: string | null;
  reason: string | null;
  created_at: string;
}

interface ApprovalOutboxItem {
  version_id: string;
  record_id: string | null;
  dataset_id: string;
  dataset_name: string;
  op: 'insert' | 'update' | 'delete';
  state: 'pending' | 'approved' | 'rejected' | 'applied' | 'superseded' | 'cancelled';
  current_step: number | null;
  step_name: string | null;
  workflow_name: string | null;
  reject_reason: string | null;
  created_at: string;
  applied_at: string | null;
}

interface InboxResponse {
  items: ApprovalInboxItem[];
  total: number;
}

interface OutboxResponse {
  items: ApprovalOutboxItem[];
  total: number;
}

// ============================================================================
// Component
// ============================================================================

export default function ApprovalsPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'inbox' | 'outbox'>('inbox');

  // Fetch inbox
  const { data: inboxData, isLoading: inboxLoading, error: inboxError } = useQuery<InboxResponse>({
    queryKey: ['approvals', 'inbox'],
    queryFn: () => api.get<InboxResponse>('/approvals/inbox'),
    enabled: activeTab === 'inbox',
  });

  // Fetch outbox
  const { data: outboxData, isLoading: outboxLoading, error: outboxError } = useQuery<OutboxResponse>({
    queryKey: ['approvals', 'outbox'],
    queryFn: () => api.get<OutboxResponse>('/approvals/outbox'),
    enabled: activeTab === 'outbox',
  });

  const isLoading = activeTab === 'inbox' ? inboxLoading : outboxLoading;
  const error = activeTab === 'inbox' ? inboxError : outboxError;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">审批中心</h1>
              <p className="mt-1 text-sm text-gray-500">管理待审批和已提交的变更</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8">
          <nav className="flex space-x-8" aria-label="Tabs">
            <button
              onClick={() => setActiveTab('inbox')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'inbox'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <span>待审批</span>
                {inboxData && inboxData.total > 0 && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    {inboxData.total}
                  </span>
                )}
              </div>
            </button>

            <button
              onClick={() => setActiveTab('outbox')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'outbox'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                <span>我的提交</span>
              </div>
            </button>
          </nav>
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
              {error instanceof Error ? error.message : '加载审批列表失败'}
            </p>
          </div>
        )}

        {!isLoading && !error && activeTab === 'inbox' && (
          <InboxList items={inboxData?.items || []} />
        )}

        {!isLoading && !error && activeTab === 'outbox' && (
          <OutboxList items={outboxData?.items || []} />
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Inbox List Component
// ============================================================================

function InboxList({ items }: { items: ApprovalInboxItem[] }) {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 className="mt-2 text-sm font-medium text-gray-900">暂无待审批项</h3>
        <p className="mt-1 text-sm text-gray-500">当前没有需要您审批的变更</p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow overflow-hidden sm:rounded-md">
      <ul className="divide-y divide-gray-200">
        {items.map((item) => (
          <li key={item.version_id}>
            <button
              onClick={() => router.push(`/approvals/${item.version_id}`)}
              className="w-full text-left block hover:bg-gray-50 transition-colors"
            >
              <div className="px-6 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-3">
                      <OperationBadge op={item.op} />
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {item.dataset_name}
                      </p>
                      <span className="text-sm text-gray-500">·</span>
                      <span className="text-sm text-gray-500">{item.workflow_name}</span>
                    </div>
                    <div className="mt-2 flex items-center space-x-4 text-sm text-gray-500">
                      <div className="flex items-center">
                        <svg className="flex-shrink-0 mr-1.5 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                        <span>{item.proposed_by_name || item.proposed_by_email || '未知用户'}</span>
                      </div>
                      <div className="flex items-center">
                        <svg className="flex-shrink-0 mr-1.5 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>{formatRelativeTime(item.created_at)}</span>
                      </div>
                      <div className="flex items-center">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                          步骤 {item.current_step + 1}: {item.step_name}
                        </span>
                      </div>
                    </div>
                    {item.reason && (
                      <p className="mt-2 text-sm text-gray-600 line-clamp-1">
                        原因：{item.reason}
                      </p>
                    )}
                  </div>
                  <div className="ml-4 flex-shrink-0">
                    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ============================================================================
// Outbox List Component
// ============================================================================

function OutboxList({ items }: { items: ApprovalOutboxItem[] }) {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
        <h3 className="mt-2 text-sm font-medium text-gray-900">暂无提交记录</h3>
        <p className="mt-1 text-sm text-gray-500">您还没有提交过任何变更</p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow overflow-hidden sm:rounded-md">
      <ul className="divide-y divide-gray-200">
        {items.map((item) => (
          <li key={item.version_id}>
            <button
              onClick={() => router.push(`/approvals/${item.version_id}`)}
              className="w-full text-left block hover:bg-gray-50 transition-colors"
            >
              <div className="px-6 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-3">
                      <OperationBadge op={item.op} />
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {item.dataset_name}
                      </p>
                      <StateBadge state={item.state} />
                    </div>
                    <div className="mt-2 flex items-center space-x-4 text-sm text-gray-500">
                      <div className="flex items-center">
                        <svg className="flex-shrink-0 mr-1.5 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>{formatRelativeTime(item.created_at)}</span>
                      </div>
                      {item.state === 'pending' && item.step_name && (
                        <div className="flex items-center">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                            步骤 {(item.current_step ?? 0) + 1}: {item.step_name}
                          </span>
                        </div>
                      )}
                      {item.workflow_name && (
                        <span className="text-gray-500">{item.workflow_name}</span>
                      )}
                    </div>
                    {item.reject_reason && (
                      <p className="mt-2 text-sm text-red-600 line-clamp-1">
                        拒绝原因：{item.reject_reason}
                      </p>
                    )}
                    {item.applied_at && (
                      <p className="mt-2 text-sm text-gray-500">
                        已应用于 {new Date(item.applied_at).toLocaleString('zh-CN')}
                      </p>
                    )}
                  </div>
                  <div className="ml-4 flex-shrink-0">
                    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ============================================================================
// Helper Components
// ============================================================================

function OperationBadge({ op }: { op: 'insert' | 'update' | 'delete' }) {
  const config = {
    insert: { label: '新增', color: 'bg-green-100 text-green-800' },
    update: { label: '修改', color: 'bg-blue-100 text-blue-800' },
    delete: { label: '删除', color: 'bg-red-100 text-red-800' },
  };

  const { label, color } = config[op];

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

function StateBadge({ state }: { state: ApprovalOutboxItem['state'] }) {
  const config: Record<ApprovalOutboxItem['state'], { label: string; color: string }> = {
    pending: { label: '待审批', color: 'bg-yellow-100 text-yellow-800' },
    approved: { label: '已批准', color: 'bg-green-100 text-green-800' },
    rejected: { label: '已拒绝', color: 'bg-red-100 text-red-800' },
    applied: { label: '已应用', color: 'bg-blue-100 text-blue-800' },
    superseded: { label: '已过期', color: 'bg-gray-100 text-gray-800' },
    cancelled: { label: '已取消', color: 'bg-gray-100 text-gray-800' },
  };

  const { label, color } = config[state];

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return '刚刚';
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  
  return date.toLocaleDateString('zh-CN');
}
