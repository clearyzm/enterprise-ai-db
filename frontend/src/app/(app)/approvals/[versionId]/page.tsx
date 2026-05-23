/**
 * Approval detail page with before/after diff and approve/reject actions.
 */

'use client';

import { useState, use } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { useAuthStore } from '@/lib/store/auth';
import DiffViewer from '@/components/diff-viewer';

interface WorkflowStep {
  name: string;
  approver: {
    type: string;
    value: string | string[] | null;
  };
  mode: 'any' | 'all';
  require_dept_match: boolean;
  condition: Record<string, unknown> | null;
}

interface ApprovalAction {
  id: string;
  version_id: string;
  step_index: number;
  approver_id: string;
  approver_email: string | null;
  approver_name: string | null;
  action: 'approve' | 'reject';
  comment: string | null;
  created_at: string;
}

interface ApprovalDetail {
  version_id: string;
  record_id: string | null;
  dataset_id: string;
  dataset_name: string;
  op: 'insert' | 'update' | 'delete';
  state: 'pending' | 'approved' | 'rejected' | 'applied' | 'superseded' | 'cancelled';
  before_payload: Record<string, unknown> | null;
  after_payload: Record<string, unknown> | null;
  current_step: number;
  workflow_id: string | null;
  workflow_name: string | null;
  workflow_steps: WorkflowStep[];
  proposed_by_id: string;
  proposed_by_email: string | null;
  proposed_by_name: string | null;
  reason: string | null;
  reject_reason: string | null;
  created_at: string;
  applied_at: string | null;
  actions: ApprovalAction[];
}

export default function ApprovalDetailPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const [comment, setComment] = useState('');
  const [showCommentInput, setShowCommentInput] = useState(false);

  const { data, isLoading, error } = useQuery<ApprovalDetail>({
    queryKey: ['approval', versionId],
    queryFn: () => api.get<ApprovalDetail>(`/approvals/${versionId}`),
  });

  const approveMutation = useMutation({
    mutationFn: () => api.post(`/approvals/${versionId}/approve`, { comment: comment || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval', versionId] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      setComment('');
      setShowCommentInput(false);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () => api.post(`/approvals/${versionId}/reject`, { comment: comment || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval', versionId] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      setComment('');
      setShowCommentInput(false);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.post(`/approvals/${versionId}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval', versionId] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
    },
  });

  const handleApprove = () => {
    if (window.confirm('确认批准此变更？')) {
      approveMutation.mutate();
    }
  };

  const handleReject = () => {
    if (!comment.trim()) {
      alert('拒绝时必须填写原因');
      return;
    }
    if (window.confirm('确认拒绝此变更？')) {
      rejectMutation.mutate();
    }
  };

  const handleCancel = () => {
    if (window.confirm('确认取消此变更？取消后无法恢复。')) {
      cancelMutation.mutate();
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

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="rounded-md bg-red-50 p-4 max-w-lg">
          <p className="text-sm font-medium text-red-800">
            {error instanceof Error ? error.message : '加载审批详情失败'}
          </p>
        </div>
      </div>
    );
  }

  const canApprove = data.state === 'pending' && user?.id !== data.proposed_by_id;
  const canCancel = data.state === 'pending' && user?.id === data.proposed_by_id;
  const isProcessing = approveMutation.isPending || rejectMutation.isPending || cancelMutation.isPending;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">审批详情</h1>
                <p className="mt-1 text-sm text-gray-500">{data.dataset_name}</p>
              </div>
            </div>
            <StateBadge state={data.state} />
          </div>
        </div>
      </div>

      <div className="px-8 py-6 max-w-7xl mx-auto">
        <div className="space-y-6">
          <MetadataCard data={data} />

          {data.workflow_steps.length > 0 && (
            <div className="bg-white shadow rounded-lg p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">审批进度</h2>
              <WorkflowProgress
                steps={data.workflow_steps}
                currentStep={data.current_step}
                actions={data.actions}
                state={data.state}
              />
            </div>
          )}

          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">变更内容</h2>
            <DiffViewer
              before={data.before_payload}
              after={data.after_payload}
              operation={data.op}
            />
          </div>

          {(canApprove || canCancel) && (
            <ActionButtons
              canApprove={canApprove}
              canCancel={canCancel}
              isProcessing={isProcessing}
              comment={comment}
              setComment={setComment}
              showCommentInput={showCommentInput}
              setShowCommentInput={setShowCommentInput}
              handleApprove={handleApprove}
              handleReject={handleReject}
              handleCancel={handleCancel}
              approveMutation={approveMutation}
              rejectMutation={rejectMutation}
              cancelMutation={cancelMutation}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function MetadataCard({ data }: { data: ApprovalDetail }) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">变更信息</h2>
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-medium text-gray-500">操作类型</dt>
          <dd className="mt-1"><OperationBadge op={data.op} /></dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">提交人</dt>
          <dd className="mt-1 text-sm text-gray-900">
            {data.proposed_by_name || data.proposed_by_email || '未知用户'}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-gray-500">提交时间</dt>
          <dd className="mt-1 text-sm text-gray-900">
            {new Date(data.created_at).toLocaleString('zh-CN')}
          </dd>
        </div>
        {data.workflow_name && (
          <div>
            <dt className="text-sm font-medium text-gray-500">审批流程</dt>
            <dd className="mt-1 text-sm text-gray-900">{data.workflow_name}</dd>
          </div>
        )}
        {data.reason && (
          <div className="sm:col-span-2">
            <dt className="text-sm font-medium text-gray-500">变更原因</dt>
            <dd className="mt-1 text-sm text-gray-900">{data.reason}</dd>
          </div>
        )}
        {data.reject_reason && (
          <div className="sm:col-span-2">
            <dt className="text-sm font-medium text-gray-500">拒绝原因</dt>
            <dd className="mt-1 text-sm text-red-600">{data.reject_reason}</dd>
          </div>
        )}
        {data.applied_at && (
          <div>
            <dt className="text-sm font-medium text-gray-500">应用时间</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {new Date(data.applied_at).toLocaleString('zh-CN')}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function ActionButtons({
  canApprove, canCancel, isProcessing, comment, setComment,
  showCommentInput, setShowCommentInput,
  handleApprove, handleReject, handleCancel,
  approveMutation, rejectMutation, cancelMutation,
}: {
  canApprove: boolean;
  canCancel: boolean;
  isProcessing: boolean;
  comment: string;
  setComment: (value: string) => void;
  showCommentInput: boolean;
  setShowCommentInput: (value: boolean) => void;
  handleApprove: () => void;
  handleReject: () => void;
  handleCancel: () => void;
  approveMutation: { error: unknown };
  rejectMutation: { error: unknown };
  cancelMutation: { error: unknown };
}) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">操作</h2>
      {showCommentInput && (
        <div className="mb-4">
          <label htmlFor="comment" className="block text-sm font-medium text-gray-700 mb-2">
            备注 {canApprove && '（拒绝时必填）'}
          </label>
          <textarea
            id="comment"
            rows={3}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            placeholder="请输入备注..."
          />
        </div>
      )}
      <div className="flex items-center space-x-4">
        {canApprove && (
          <>
            <button
              onClick={() => { setShowCommentInput(true); handleApprove(); }}
              disabled={isProcessing}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
            >
              批准
            </button>
            <button
              onClick={() => {
                if (!showCommentInput) { setShowCommentInput(true); }
                else { handleReject(); }
              }}
              disabled={isProcessing}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            >
              拒绝
            </button>
          </>
        )}
        {canCancel && (
          <button
            onClick={handleCancel}
            disabled={isProcessing}
            className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            取消提交
          </button>
        )}
        {!showCommentInput && canApprove && (
          <button onClick={() => setShowCommentInput(true)} className="text-sm text-blue-600 hover:text-blue-700">
            添加备注
          </button>
        )}
      </div>
      {(approveMutation.error || rejectMutation.error || cancelMutation.error) && (
        <div className="mt-4 rounded-md bg-red-50 p-4">
          <p className="text-sm text-red-800">
            {approveMutation.error instanceof Error ? approveMutation.error.message
              : rejectMutation.error instanceof Error ? rejectMutation.error.message
              : cancelMutation.error instanceof Error ? cancelMutation.error.message
              : '操作失败'}
          </p>
        </div>
      )}
    </div>
  );
}

function StateBadge({ state }: { state: ApprovalDetail['state'] }) {
  const config: Record<ApprovalDetail['state'], { label: string; color: string }> = {
    pending: { label: '待审批', color: 'bg-yellow-100 text-yellow-800' },
    approved: { label: '已批准', color: 'bg-green-100 text-green-800' },
    rejected: { label: '已拒绝', color: 'bg-red-100 text-red-800' },
    applied: { label: '已应用', color: 'bg-blue-100 text-blue-800' },
    superseded: { label: '已过期', color: 'bg-gray-100 text-gray-800' },
    cancelled: { label: '已取消', color: 'bg-gray-100 text-gray-800' },
  };
  const { label, color } = config[state];
  return <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${color}`}>{label}</span>;
}

function OperationBadge({ op }: { op: 'insert' | 'update' | 'delete' }) {
  const config = {
    insert: { label: '新增', color: 'bg-green-100 text-green-800' },
    update: { label: '修改', color: 'bg-blue-100 text-blue-800' },
    delete: { label: '删除', color: 'bg-red-100 text-red-800' },
  };
  const { label, color } = config[op];
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>{label}</span>;
}

function WorkflowProgress({
  steps, currentStep, actions, state,
}: {
  steps: WorkflowStep[];
  currentStep: number;
  actions: ApprovalAction[];
  state: ApprovalDetail['state'];
}) {
  return (
    <div className="space-y-4">
      {steps.map((step, index) => {
        const stepActions = actions.filter((a) => a.step_index === index);
        const isCurrentStep = index === currentStep && state === 'pending';
        const isPastStep = index < currentStep || state !== 'pending';

        return (
          <div key={index} className="flex items-start space-x-4">
            <div className="flex-shrink-0">
              {isPastStep ? (
                <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
                  <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              ) : isCurrentStep ? (
                <div className="w-8 h-8 rounded-full bg-yellow-500 flex items-center justify-center">
                  <span className="text-sm font-medium text-white">{index + 1}</span>
                </div>
              ) : (
                <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center">
                  <span className="text-sm font-medium text-gray-600">{index + 1}</span>
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-medium text-gray-900">{step.name}</h3>
                {isCurrentStep && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                    进行中
                  </span>
                )}
              </div>
              {stepActions.length > 0 && (
                <div className="mt-2 space-y-2">
                  {stepActions.map((action) => (
                    <div key={action.id} className="text-sm">
                      <span className={action.action === 'approve' ? 'text-green-600' : 'text-red-600'}>
                        {action.action === 'approve' ? '✓ 已批准' : '✗ 已拒绝'}
                      </span>
                      <span className="text-gray-500 ml-2">
                        {action.approver_name || action.approver_email}
                      </span>
                      {action.comment && <p className="text-gray-600 mt-1">{action.comment}</p>}
                      <p className="text-gray-400 text-xs mt-1">
                        {new Date(action.created_at).toLocaleString('zh-CN')}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}