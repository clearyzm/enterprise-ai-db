/**
 * AI Conversations list page.
 * 
 * Features:
 * - List all user's conversations
 * - Create new conversation
 * - Navigate to conversation detail
 * - Delete conversation
 * - Auto-create default conversation if none exists
 */

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

interface ConversationsResponse {
  conversations: Conversation[];
  total: number;
}

// ============================================================================
// Component
// ============================================================================

export default function AIPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Fetch conversations
  const { data, isLoading, error } = useQuery<ConversationsResponse>({
    queryKey: ['ai', 'conversations'],
    queryFn: () => api.get<ConversationsResponse>('/ai/conversations'),
  });

  // Create conversation mutation
  const createMutation = useMutation({
    mutationFn: (title?: string) => api.post<Conversation>('/ai/conversations', { title }),
    onSuccess: (newConversation) => {
      queryClient.invalidateQueries({ queryKey: ['ai', 'conversations'] });
      router.push(`/ai/${newConversation.id}`);
    },
  });

  // Delete conversation mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/ai/conversations/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai', 'conversations'] });
    },
  });

  // Auto-create default conversation if none exists
  useEffect(() => {
    if (data && data.conversations.length === 0 && !createMutation.isPending) {
      createMutation.mutate('新对话');
    }
  }, [data, createMutation]);

  const handleNewConversation = () => {
    createMutation.mutate('新对话');
  };

  const handleDelete = (id: string, title: string | null) => {
    if (window.confirm(`确认删除对话"${title || '未命名对话'}"？`)) {
      deleteMutation.mutate(id);
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
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="rounded-md bg-red-50 p-4 max-w-lg">
          <p className="text-sm font-medium text-red-800">
            {error instanceof Error ? error.message : '加载对话列表失败'}
          </p>
        </div>
      </div>
    );
  }

  // If auto-creating first conversation, show loading
  if (data && data.conversations.length === 0 && createMutation.isPending) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="text-gray-500">创建对话中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">AI 助手</h1>
              <p className="mt-1 text-sm text-gray-500">与 AI 对话，查询和分析数据</p>
            </div>
            <button
              onClick={handleNewConversation}
              disabled={createMutation.isPending}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              新建对话
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-8 py-6">
        {data && data.conversations.length === 0 ? (
          <div className="text-center py-12">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900">暂无对话</h3>
            <p className="mt-1 text-sm text-gray-500">开始与 AI 助手对话</p>
            <div className="mt-6">
              <button
                onClick={handleNewConversation}
                disabled={createMutation.isPending}
                className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                新建对话
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data?.conversations.map((conversation) => (
              <ConversationCard
                key={conversation.id}
                conversation={conversation}
                onDelete={handleDelete}
                isDeleting={deleteMutation.isPending}
              />
            ))}
          </div>
        )}

        {createMutation.error && (
          <div className="mt-4 rounded-md bg-red-50 p-4">
            <p className="text-sm text-red-800">
              {createMutation.error instanceof Error ? createMutation.error.message : '创建对话失败'}
            </p>
          </div>
        )}

        {deleteMutation.error && (
          <div className="mt-4 rounded-md bg-red-50 p-4">
            <p className="text-sm text-red-800">
              {deleteMutation.error instanceof Error ? deleteMutation.error.message : '删除对话失败'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Conversation Card Component
// ============================================================================

function ConversationCard({
  conversation,
  onDelete,
  isDeleting,
}: {
  conversation: Conversation;
  onDelete: (id: string, title: string | null) => void;
  isDeleting: boolean;
}) {
  const router = useRouter();

  return (
    <div className="bg-white rounded-lg border border-gray-200 hover:border-blue-500 hover:shadow-md transition-all">
      <button
        onClick={() => router.push(`/ai/${conversation.id}`)}
        className="w-full text-left p-6"
      >
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 truncate">
              {conversation.title || '未命名对话'}
            </h3>
            <p className="mt-2 text-sm text-gray-500">
              {new Date(conversation.updated_at).toLocaleString('zh-CN')}
            </p>
          </div>
          <svg className="flex-shrink-0 ml-2 w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </div>
      </button>
      
      <div className="px-6 pb-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(conversation.id, conversation.title);
          }}
          disabled={isDeleting}
          className="text-sm text-red-600 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          删除
        </button>
      </div>
    </div>
  );
}
